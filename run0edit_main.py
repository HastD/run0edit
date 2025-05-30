#!/usr/bin/env python3

"""
run0edit - edit a single file as root.

Please report issues at: https://github.com/HastD/run0edit/issues

Copyright (C) 2025 Daniel Hast

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import argparse
import os
import pathlib
import shutil
import subprocess  # nosec
import sys
import textwrap
import tempfile

from collections.abc import Sequence
from typing import Final, Union

__version__: Final[str] = "0.5.0"
INNER_SCRIPT_PATH: Final[str] = "/usr/libexec/run0edit/run0edit_inner.py"


def readonly_filesystem(path: str) -> Union[bool, None]:
    """Determine if the path is on a read-only filesystem."""
    # pylint: disable=duplicate-code
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return None


def find_command(command: str) -> Union[str, None]:
    """Search for command using a default path."""
    # pylint: disable=duplicate-code
    return shutil.which(command, path=os.defpath)


def is_valid_executable(path: str) -> bool:
    """Test if path is an absolute path to an executable"""
    is_rx = os.F_OK | os.R_OK | os.X_OK
    return os.path.isabs(path) and os.path.isfile(path) and os.access(path, is_rx)


def editor_path(
    *,
    conf_paths: Union[Sequence[str], None] = None,
    fallbacks: Union[Sequence[str], None] = None,
) -> Union[str, None]:
    """Get path to editor executable."""
    if conf_paths is None:
        conf_paths = ("/etc/run0edit/editor.conf",)
    for conf_path in conf_paths:
        try:
            with open(conf_path, "r", encoding="utf8") as f:
                editor = f.read().strip()
        except OSError:
            continue
        if is_valid_executable(editor):
            return editor
    if fallbacks is None:
        fallbacks = ("nano", "vi")
    for fallback in fallbacks:
        editor = find_command(fallback)
        if editor is not None:
            return editor
    return None


def directory_does_not_exist(path: str) -> Union[bool, None]:
    """
    Check if the directory containing the path definitely does not exist.
    Returns None if unable to determine (e.g. due to permission issues).
    """
    real_path = pathlib.Path(path).resolve()
    partial = pathlib.Path("/")
    # Walk the directory tree from the filesystem root to the target directory
    for part in real_path.parts[1:-1]:
        try:
            if part not in os.listdir(partial):
                # Next directory doesn't exist
                return True
        except NotADirectoryError:
            return True
        except OSError:
            # Current directory exists but we don't have permission to list its contents
            return None
        partial = partial / part
    if os.access(real_path.parent, os.F_OK):
        # If parent is not a directory then path is invalid so return True
        return not os.path.isdir(real_path.parent)
    # Parent exists but unable to determine if it's a directory
    return None


def make_temp_file(path: str) -> str:
    """Create a temporary file with a random suffix appended to the filename."""
    name = os.path.basename(path)
    return tempfile.mkstemp(prefix=f"{name:.64}.")[1]


def clean_temp_file(path: str, *, only_if_empty: bool = False):
    """Remove the temporary file (optionally only if empty)."""
    if not only_if_empty or os.path.getsize(path) == 0:
        os.remove(path)


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
    if os.path.exists(path):
        rw_path = path
    else:
        rw_path = os.path.dirname(path)
    return os.path.realpath(rw_path)


class MissingCommandError(Exception):
    """A command essential for running the program was not found."""


def build_run0_arguments(
    path: str, temp_path: str, editor: str, *, debug: bool = False
) -> list[str]:
    """Construct the arguments to be passed to run0."""
    run0_cmd = find_command("run0")
    if run0_cmd is None:
        raise MissingCommandError("run0")
    python_cmd = find_command("python3")
    if python_cmd is None:
        raise MissingCommandError("python3")
    args = [run0_cmd, f'--description=run0edit "{path}"']
    for systemd_property in SYSTEMD_SANDBOX_PROPERTIES:
        args.append(f"--property={systemd_property}")
    rw_path = sandbox_path(path)
    args += [
        f'--property=ReadWritePaths="{escape_path(rw_path)}" "{escape_path(temp_path)}"',
        python_cmd,
        INNER_SCRIPT_PATH,
        path,
        temp_path,
        editor,
    ]
    if debug:
        args.append("--debug")
    return args


def print_err(message: str):
    """Print error message to stderr with text wrapping."""
    print("\n".join(textwrap.wrap(f"run0edit: {message.strip()}")), file=sys.stderr)


def validate_path(path: str) -> Union[str, None]:
    """
    Check if the path is valid (returning None) or if we should terminate
    early with error message (returned as a string).
    """
    if os.path.isdir(path):
        return f"{path} is a directory."
    if os.path.isfile(path) and os.access(path, os.R_OK | os.W_OK):
        return f"{path} is writable by the current user; run0edit is unnecessary."
    directory = os.path.dirname(path)
    if directory_does_not_exist(path):
        return f"No such directory {directory}"
    readonly = readonly_filesystem(path)
    if readonly is None:
        readonly = readonly_filesystem(directory)
    if readonly:
        return f"{path} is on a read-only filesystem."
    return None


def run(path: str, editor: str, *, debug: bool = False) -> int:
    """Main program to run for a given file."""
    path = os.path.realpath(path)
    result = validate_path(path)
    if result is not None:
        print_err(result)
        return 1
    temp_filename = make_temp_file(path)
    run0_args = build_run0_arguments(path, temp_filename, editor, debug=debug)
    env = os.environ.copy()
    env["SYSTEMD_ADJUST_TERMINAL_TITLE"] = "false"
    process = subprocess.run(run0_args, env=env, check=False)  # nosec
    if process.returncode == 226:
        # If directory does not exist, namespace creation will fail, causing
        # run0 to fail with exit status 226:
        # https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
        print_err(f"No such directory {os.path.dirname(path)}")
        clean_temp_file(temp_filename)
        return 1
    if process.returncode != 0:
        clean_temp_file(temp_filename, only_if_empty=True)
        return process.returncode
    clean_temp_file(temp_filename)
    return 0


def main() -> int:
    """Main function. Return value becomes the exit code."""
    description = "run0edit allows a permitted user to edit a file as root."
    epilog = "The default choice of text editor may be configured at /etc/run0edit/editor.conf"
    parser = argparse.ArgumentParser(prog="run0edit", description=description, epilog=epilog)
    parser.add_argument("-v", "--version", action="version", version=f"run0edit {__version__}")
    parser.add_argument("--editor", help="absolute path to text editor (optional)")
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("paths", nargs="+", metavar="FILE", help="path to the file to be edited")
    args = parser.parse_args()
    if args.editor is not None:
        if is_valid_executable(args.editor):
            editor = os.path.realpath(args.editor)
        else:
            print_err("--editor must be an absolute path to an executable file")
            return 1
    else:
        editor = editor_path()
    if editor is None:
        print_err("""
            Editor not found. Please install either nano or vi, or write the path to
            the text editor of your choice to /etc/run0edit/editor.conf
        """)
        return 1
    exit_code = 0
    for path in args.paths:
        try:
            exit_code = run(path, editor, debug=args.debug)
        except MissingCommandError as e:
            print_err(f"command `{e.args[0]}` not found")
            if args.debug:
                raise e
            return 1
        if exit_code != 0:
            break
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
