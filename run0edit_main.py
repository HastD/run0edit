#!/usr/bin/env python3

"""
run0edit - edit a single file as root.

Please report issues at: https://github.com/HastD/run0edit/issues

Copyright (C) 2025 Daniel Hast

SPDX-License-Identifier: MIT OR Apache-2.0

-----

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the “Software”), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

-----

Licensed under the Apache License, Version 2.0 (the "License").
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import argparse
import dataclasses
import enum
import hashlib
import os
import pathlib
import stat
import shutil
import subprocess  # nosec
import sys
import textwrap
import tempfile

from collections.abc import Sequence
from typing import Final, Union

__version__: Final[str] = "0.5.0"
INNER_SCRIPT_PATH: Final[str] = "/usr/libexec/run0edit/run0edit_inner.py"
INNER_SCRIPT_SHA256: Final[str] = "12bb6b9f8f0f52bd1b578c265c36698bfd4f2b4e83a5907f433be349775b26e6"


def validate_inner_script() -> bool:
    """Ensure inner script has expected SHA256 hash."""
    try:
        with open(INNER_SCRIPT_PATH, "rb") as f:
            file_hash = hashlib.sha256(f.read())
    except OSError:
        return False
    return file_hash.hexdigest() == INNER_SCRIPT_SHA256


def readonly_filesystem(path: str) -> Union[bool, None]:
    """Determine if the path is on a read-only filesystem."""
    # pylint: disable=duplicate-code
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return None


class CommandNotFoundError(Exception):
    """An external command was not found."""


def find_command(command: str) -> str:
    """Search for command using a default path."""
    # pylint: disable=duplicate-code
    cmd_path = shutil.which(command, path="/usr/bin:/bin")
    if cmd_path is None:
        raise CommandNotFoundError(command)
    return cmd_path


def is_valid_executable(path: str) -> bool:
    """Test if path is an absolute path to an executable"""
    is_rx = os.R_OK | os.X_OK
    return os.path.isabs(path) and os.path.isfile(path) and os.access(path, is_rx)


class EditorNotFoundError(Exception):
    """Provided editor path is invalid."""


def get_editor_path_from_conf(
    *,
    conf_path: str = "/etc/run0edit/editor.conf",
    fallbacks: Union[Sequence[str], None] = None,
) -> str:
    """Get path to editor executable."""
    try:
        with open(conf_path, "r", encoding="utf8") as f:
            editor = f.read().strip()
    except OSError:
        pass
    else:
        if is_valid_executable(editor):
            return editor
    if fallbacks is None:
        fallbacks = ("nano", "vi")
    for fallback in fallbacks:
        try:
            return find_command(fallback)
        except CommandNotFoundError:
            pass
    raise EditorNotFoundError


class InvalidEditorError(Exception):
    """Provided editor path is invalid."""


def get_editor_path(provided_editor: Union[str, None] = None) -> str:
    """Get the editor path from either a provided path or conf file."""
    if provided_editor is None:
        return get_editor_path_from_conf()
    if not is_valid_executable(provided_editor):
        raise InvalidEditorError(provided_editor)
    return os.path.realpath(provided_editor)


class PathExists(enum.Enum):
    """Possibilities for whether a path exists."""

    YES = enum.auto()
    NO = enum.auto()
    MAYBE = enum.auto()

    @classmethod
    def from_bool(cls, cond: bool):
        """Convert bool to PathExists"""
        return cls.YES if cond else cls.NO


def check_directory_existence(path: str) -> PathExists:
    """Check whether the directory containing the path exists."""
    real_path = pathlib.Path(path).resolve()
    partial = pathlib.Path("/")
    # Walk the directory tree from the filesystem root to the target directory
    for part in real_path.parts[1:-1]:
        try:
            if part not in os.listdir(partial):
                # Next directory doesn't exist
                return PathExists.NO
        except NotADirectoryError:
            return PathExists.NO
        except OSError:
            # Current directory exists but we don't have permission to list its contents
            return PathExists.MAYBE
        partial = partial / part
    try:
        parent_mode = os.stat(real_path.parent).st_mode
    except OSError:
        # Parent exists but unable to determine if it's a directory
        return PathExists.MAYBE
    # If parent is not a directory then path is invalid, otherwise directory exists.
    return PathExists.from_bool(stat.S_ISDIR(parent_mode))


class TempFile:
    """A temporary file."""

    def __init__(self, filename: str):
        """Create a temporary file with a random suffix appended to the given filename."""
        self.directory = tempfile.mkdtemp(prefix="run0edit-")
        name = os.path.basename(filename)
        self.path = tempfile.mkstemp(prefix=f"{name:.64}.", dir=self.directory)[1]

    def remove(self, *, only_if_empty: bool = False):
        """Delete the temporary file"""
        if not only_if_empty or os.path.getsize(self.path) == 0:
            os.remove(self.path)
            os.rmdir(self.directory)


def escape_path(path: str) -> str:
    """Escape a path for use in a systemd property string."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


SYSTEMD_SANDBOX_PROPERTIES: Final[list[str]] = [
    "CapabilityBoundingSet=CAP_DAC_OVERRIDE CAP_FOWNER CAP_LINUX_IMMUTABLE",
    "DevicePolicy=closed",
    "LockPersonality=yes",
    "MemoryDenyWriteExecute=yes",
    "NoNewPrivileges=yes",
    "PrivateDevices=yes",
    "PrivateIPC=yes",
    "PrivateNetwork=yes",
    "ProcSubset=pid",
    "ProtectClock=yes",
    "ProtectControlGroups=yes",
    "ProtectHome=read-only",
    "ProtectHostname=yes",
    "ProtectKernelLogs=yes",
    "ProtectKernelModules=yes",
    "ProtectKernelTunables=yes",
    "ProtectProc=noaccess",
    "ProtectSystem=strict",
    "RestrictAddressFamilies=AF_UNIX",
    "RestrictNamespaces=yes",
    "RestrictRealtime=yes",
    "RestrictSUIDSGID=yes",
    "SystemCallArchitectures=native",
    "SystemCallFilter=@system-service",
    "SystemCallFilter=~memfd_create @mount @privileged",
]


def sandbox_path(path: str) -> str:
    """Get the path to be passed to ReadWritePaths"""
    return path if os.path.exists(path) else os.path.dirname(path)


@dataclasses.dataclass
class Run0Arguments:
    """Arguments to be passed to run0."""

    description: str
    systemd_properties: list[str]
    command: str
    command_args: list[str]
    _run0_cmd: str = dataclasses.field(default_factory=lambda: find_command("run0"))

    def argument_list(self) -> list[str]:
        """Build the argument list that can be executed."""
        args = [self._run0_cmd, f"--description={self.description}"]
        args += [f"--property={prop}" for prop in self.systemd_properties]
        args += ["--", self.command] + self.command_args
        return args


def build_run0_arguments(
    path: str, temp_path: str, editor: str, *, debug: bool = False
) -> Run0Arguments:
    """Construct the arguments to be passed to run0."""
    python_cmd = find_command("python3")
    rw_path = sandbox_path(path)
    rw_path_prop = f'ReadWritePaths="{escape_path(rw_path)}" "{escape_path(temp_path)}"'
    systemd_properties = SYSTEMD_SANDBOX_PROPERTIES + [rw_path_prop]
    python_args = [INNER_SCRIPT_PATH, path, temp_path, editor]
    if debug:
        python_args.append("--debug")
    return Run0Arguments(
        description=f'run0edit "{path}"',
        systemd_properties=systemd_properties,
        command=python_cmd,
        command_args=python_args,
    )


def print_err(message: str):
    """Print error message to stderr with text wrapping."""
    text = textwrap.fill("run0edit: " + textwrap.dedent(message.strip("\n")), width=80)
    print(text, file=sys.stderr)


class InvalidPathError(Exception):
    """The provided path is not suitable for use with run0edit."""

    @property
    def reason(self) -> str:
        """Reason why the path is invalid."""
        return str(self.args[0] if self.args else "invalid path")


def validate_path(path: str):
    """Raise an InvalidPathError if path is invalid and we should return early."""
    if os.path.isdir(path):
        raise InvalidPathError(f"{path} is a directory.")
    if os.path.isfile(path) and os.access(path, os.R_OK | os.W_OK):
        raise InvalidPathError(f"{path} is writable by the current user; run0edit is unnecessary.")
    directory = os.path.dirname(path)
    if check_directory_existence(path) == PathExists.NO:
        raise InvalidPathError(f"No such directory {directory}")
    readonly = readonly_filesystem(path)
    if readonly is None:
        readonly = readonly_filesystem(directory)
    if readonly:
        raise InvalidPathError(f"{path} is on a read-only filesystem.")


def run(path: str, editor: str, *, debug: bool = False) -> int:
    """Main program to run for a given file."""
    path = os.path.realpath(path)
    try:
        validate_path(path)
    except InvalidPathError as e:
        print_err(e.reason)
        return 1
    temp_file = TempFile(path)
    run0_args = build_run0_arguments(path, temp_file.path, editor, debug=debug)
    env = os.environ.copy()
    if os.geteuid() == 0:
        env["SYSTEMD_ADJUST_TERMINAL_TITLE"] = "false"
    process = subprocess.run(run0_args.argument_list(), env=env, check=False)  # nosec
    if process.returncode == 226:
        # If directory does not exist, namespace creation will fail, causing
        # run0 to fail with exit status 226:
        # https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
        print_err(f"No such directory {os.path.dirname(path)}")
        temp_file.remove()
        return 1
    if process.returncode != 0:
        temp_file.remove(only_if_empty=True)
        return process.returncode
    temp_file.remove()
    return 0


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments using argparse."""
    description = "run0edit allows a permitted user to edit a file as root."
    epilog = "The default choice of text editor may be configured at /etc/run0edit/editor.conf"
    parser = argparse.ArgumentParser(prog="run0edit", description=description, epilog=epilog)
    parser.add_argument("-v", "--version", action="version", version=f"run0edit {__version__}")
    parser.add_argument("--editor", help="absolute path to text editor (optional)")
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("paths", nargs="+", metavar="FILE", help="path to the file to be edited")
    return parser.parse_args()


def main() -> int:
    """Main function. Return value becomes the exit code."""
    args = parse_arguments()
    if not validate_inner_script():
        print_err(f"""
            ERROR: Inner script was not found at {INNER_SCRIPT_PATH} or did not
            have expected SHA-256 hash!
        """)
        return 1
    try:
        editor = get_editor_path(provided_editor=args.editor)
    except EditorNotFoundError:
        print_err("""
            Editor not found. Please install either nano or vi, or write the path to
            the text editor of your choice to /etc/run0edit/editor.conf
        """)
        return 1
    except InvalidEditorError:
        print_err("--editor must be an absolute path to an executable file")
        return 1
    exit_code = 0
    for path in args.paths:
        try:
            exit_code = run(path, editor, debug=args.debug)
        except CommandNotFoundError as e:
            print_err(f"command `{e.args[0]}` not found")
            if args.debug:
                raise e
            return 1
        if exit_code != 0:
            break
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
