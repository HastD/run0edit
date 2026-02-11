#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
run0edit - edit a single file as root.

Please report issues at: https://github.com/HastD/run0edit/issues
"""

import argparse
import dataclasses
import enum
import hashlib
import os
import pathlib
import shutil
import stat
import subprocess  # nosec
import sys
import tempfile
import textwrap
from collections.abc import Sequence
from typing import Final

__version__: Final[str] = "0.5.7"
INNER_SCRIPT_PATH: Final[str] = "/usr/libexec/run0edit/run0edit_inner.py"
INNER_SCRIPT_B2: Final[str] = "\
9f596fb81d6b422fc2a53d9bde907f90daca814f9fd6107169dea8ed0e01e5740fbe22eb75dfc463a7762a64fd189fd3eb0799edfece8470ea566d50d68eade6"
DEFAULT_CONF_PATH: Final[str] = "/etc/run0edit/editor.conf"

SYSTEM_CALL_DENY: Final[list[str]] = [
    "@aio",
    "@chown",
    "@keyring",
    "@memlock",
    "@mount",
    "@privileged",
    "@resources",
    "@setuid",
    "memfd_create",
]

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
    "ProtectHostname=yes",
    "ProtectKernelLogs=yes",
    "ProtectKernelModules=yes",
    "ProtectKernelTunables=yes",
    "ProtectProc=noaccess",
    "ReadOnlyPaths=/",
    "RestrictAddressFamilies=AF_UNIX",
    "RestrictNamespaces=yes",
    "RestrictRealtime=yes",
    "RestrictSUIDSGID=yes",
    "SystemCallArchitectures=native",
    "SystemCallFilter=@system-service",
    f"SystemCallFilter=~{' '.join(SYSTEM_CALL_DENY)}",
    "SystemCallErrorNumber=EPERM",
]


def validate_inner_script() -> bool:
    """Ensure inner script has expected BLAKE2 hash."""
    try:
        with open(INNER_SCRIPT_PATH, "rb") as f:
            file_hash = hashlib.blake2b(f.read())
    except OSError:
        return False
    return file_hash.hexdigest() == INNER_SCRIPT_B2


def readonly_filesystem(path: str) -> bool | None:
    """Determine if the path is on a read-only filesystem."""
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return None


class CommandNotFoundError(Exception):
    """An external command was not found."""


def find_command(command: str) -> str:
    """Search for command using a default path."""
    cmd_path = shutil.which(command, path="/usr/bin:/bin")
    if cmd_path is None:
        raise CommandNotFoundError(command)
    return cmd_path


def is_valid_executable(path: str) -> bool:
    """Test if path is an absolute path to an executable"""
    is_rx = os.R_OK | os.X_OK
    return os.path.isabs(path) and os.path.isfile(path) and os.access(path, is_rx)


class EditorSelectionError(Exception):
    """Parent class for exceptions involving editor selection."""


class EditorNotFoundError(EditorSelectionError):
    """Could not find a valid editor."""


class UnreadableEditorConfError(EditorSelectionError):
    """Editor conf file exists but is unreadable by the current user."""


class InvalidEditorConfError(EditorSelectionError):
    """Editor path in conf file is invalid."""


class InvalidProvidedEditorError(EditorSelectionError):
    """Provided editor path is invalid."""


def get_editor_path_from_conf(conf_path: str = DEFAULT_CONF_PATH) -> str | None:
    """Get path to editor executable from conf file."""
    try:
        with open(conf_path, encoding="utf8") as f:
            editor = f.read().strip()
    except PermissionError as e:
        raise UnreadableEditorConfError from e
    except OSError:
        return None
    if not editor:
        return None
    if not is_valid_executable(editor):
        raise InvalidEditorConfError(editor)
    return editor


def get_editor_path_from_env() -> str | None:
    """Get path to editor executable from environment variables."""
    for env_var in ("VISUAL", "EDITOR"):
        editor_path = os.environ.get(env_var)
        if editor_path is not None and is_valid_executable(editor_path):
            return editor_path

    return None


def get_fallback_editor_path(fallbacks: Sequence[str] | None = None) -> str | None:
    """Get fallback editor path."""
    if fallbacks is None:
        fallbacks = ("nano", "vi")
    for fallback in fallbacks:
        try:
            return find_command(fallback)
        except CommandNotFoundError:
            pass
    return None


def get_editor_path(provided_editor: str | None = None) -> str:
    """Get the editor path from a provided path, conf file, or fallback."""
    if provided_editor is not None:
        if not is_valid_executable(provided_editor):
            raise InvalidProvidedEditorError(provided_editor)
        return os.path.realpath(provided_editor)
    editor = get_editor_path_from_env()
    if editor is not None:
        return editor
    editor = get_editor_path_from_conf()
    if editor is not None:
        return editor
    editor = get_fallback_editor_path()
    if editor is not None:
        return editor
    raise EditorNotFoundError


def handle_editor_selection(provided_editor: str | None = None) -> str:
    """Get editor path, handling errors by printing error messages and re-raising."""
    try:
        return get_editor_path(provided_editor=provided_editor)
    except EditorNotFoundError:
        print_err(f"""
            Editor not found. Please install either nano or vi, or write the path to
            the text editor of your choice to {DEFAULT_CONF_PATH}
        """)
        raise
    except UnreadableEditorConfError:
        conf_dir = os.path.dirname(DEFAULT_CONF_PATH)
        print_err(
            f"""
            Configuration file exists but is unreadable. Please fix the permissions on
            {DEFAULT_CONF_PATH} to make the file readable by all users. To do so, run the
            following command as root:
                chmod 0755 {conf_dir} && chmod 0644 {DEFAULT_CONF_PATH}
            You may also use the --editor option to specify the editor to use for a single
            run of run0edit.
            """,
            wrap=False,
        )
        raise
    except InvalidEditorConfError:
        print_err(f"""
            Configuration file has an invalid editor. Please edit {DEFAULT_CONF_PATH}
            to contain an absolute path to the executable that you want run0edit to use
            as a text editor. You may also use the --editor option to specify the
            editor to use for a single run of run0edit.
        """)
        raise
    except InvalidProvidedEditorError:
        print_err("--editor must be an absolute path to an executable file")
        raise


class PathExists(enum.Enum):
    """Possibilities for whether a path exists."""

    YES = enum.auto()
    NO = enum.auto()
    MAYBE = enum.auto()

    @classmethod
    def from_bool(cls, cond: bool) -> "PathExists":
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

    def remove(self, *, only_if_empty: bool = False) -> None:
        """Delete the temporary file"""
        if not only_if_empty or os.path.getsize(self.path) == 0:
            os.remove(self.path)
            os.rmdir(self.directory)


def escape_path(path: str) -> str:
    """Escape a path for use in a systemd property string."""
    return path.replace("\\", "\\\\").replace('"', '\\"')


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
    setenv: dict[str, str] = dataclasses.field(default_factory=dict)
    extra_options: list[str] = dataclasses.field(default_factory=list)
    _run0_cmd: str = dataclasses.field(default_factory=lambda: find_command("run0"))

    def argument_list(self) -> list[str]:
        """Build the argument list that can be executed."""
        args = [self._run0_cmd, f"--description={self.description}"]
        args += [f"--property={prop}" for prop in self.systemd_properties]
        for key, value in self.setenv.items():
            args.append(f"--setenv={key}={value}")
        args += self.extra_options
        args += ["--", self.command, *self.command_args]
        return args


def build_run0_arguments(
    path: str,
    temp_path: str,
    editor: str,
    *,
    bgcolor: str | None = None,
    debug: bool = False,
    no_prompt: bool = False,
) -> Run0Arguments:
    """Construct the arguments to be passed to run0."""
    python_cmd = find_command("python3")
    rw_path = sandbox_path(path)
    rw_path_prop = f'ReadWritePaths="{escape_path(rw_path)}" "{escape_path(temp_path)}"'
    systemd_properties = [*SYSTEMD_SANDBOX_PROPERTIES, rw_path_prop]
    extra_options = []
    python_args = [INNER_SCRIPT_PATH, path, temp_path, editor]
    if bgcolor is not None:
        extra_options.append(f"--background={bgcolor}")
        python_args.append(bgcolor)
    setenv = {}
    if debug:
        setenv["RUN0EDIT_DEBUG"] = "1"
    if no_prompt:
        setenv["RUN0EDIT_NO_PROMPT"] = "1"
    return Run0Arguments(
        description=f'run0edit "{path}"',
        systemd_properties=systemd_properties,
        command=python_cmd,
        command_args=python_args,
        extra_options=extra_options,
        setenv=setenv,
    )


def print_err(message: str, *, wrap: bool = True) -> None:
    """Print error message to stderr with text wrapping."""
    text = "run0edit: " + textwrap.dedent(message.strip("\n"))
    if wrap:
        text = textwrap.fill(text, width=80)
    print(text, file=sys.stderr)


class InvalidPathError(Exception):
    """The provided path is not suitable for use with run0edit."""

    @property
    def reason(self) -> str:
        """Reason why the path is invalid."""
        return str(self.args[0] if self.args else "invalid path")


def validate_path(path: str) -> None:
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


def run(
    path: str,
    editor: str,
    *,
    bgcolor: str | None = None,
    debug: bool = False,
    no_prompt: bool = False,
) -> int:
    """Main program to run for a given file."""
    path = os.path.realpath(path)
    try:
        validate_path(path)
    except InvalidPathError as e:
        print_err(e.reason)
        return 1
    temp_file = TempFile(path)
    run0_args = build_run0_arguments(
        path, temp_file.path, editor, bgcolor=bgcolor, debug=debug, no_prompt=no_prompt
    )
    env = os.environ.copy()
    if os.geteuid() == 0:
        env["SYSTEMD_ADJUST_TERMINAL_TITLE"] = "false"
    process = subprocess.run(run0_args.argument_list(), env=env, check=False)  # nosec
    match process.returncode:
        case 0:
            temp_file.remove()
            return 0
        case 226:
            # If directory does not exist, namespace creation will fail, causing
            # run0 to fail with exit status 226:
            # https://www.freedesktop.org/software/systemd/man/latest/systemd.exec.html
            # This can also occur if the path is privileged (such as /etc/shadow)
            # and SELinux is enabled and blocks systemd from mounting the namespace.
            print_err(
                f"No such directory {os.path.dirname(path)}, or path is in a privileged location."
            )
            temp_file.remove()
            return 1
        case _:
            temp_file.remove(only_if_empty=True)
            return process.returncode


def ansi_color(color: str) -> str:
    """
    Return string unmodified if formatted like an ANSI color code, otherwise raise ValueError.
    """
    if color and not all(part.isascii() and part.isdigit() for part in color.split(";")):
        raise ValueError
    return color


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments using argparse."""
    description = "run0edit allows a permitted user to edit a file as root."
    epilog = f"""\
    The default choice of text editor may be configured at {DEFAULT_CONF_PATH},
    or by setting the VISUAL or EDITOR environment variables."
    """
    parser = argparse.ArgumentParser(prog="run0edit", description=description, epilog=epilog)
    parser.add_argument("-v", "--version", action="version", version=f"run0edit {__version__}")
    parser.add_argument("--editor", help="absolute path to text editor")
    parser.add_argument(
        "--background",
        type=ansi_color,
        metavar="COLOR",
        help="set ANSI color for background (empty for none)",
    )
    parser.add_argument("--no-prompt", action="store_true", help="skip confirmation prompts")
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("paths", nargs="+", metavar="FILE", help="path to the file to be edited")
    return parser.parse_args()


class UsageError(Exception):
    """Incorrect usage of run0edit command."""


def catch_usage_mistake(paths: list[str], *, prompt: bool = True) -> None:
    """
    Check if the user has likely made a usage mistake by passing an executable as the
    first argument.
    """
    if not prompt or len(paths) <= 1:
        return
    arg = paths[0]
    if os.sep in arg or shutil.which(arg) is None:
        return
    print_err(f"""
        Warning: `{arg}` looks like an executable command. If you intended to run {arg}
        as a text editor, use the --editor option or (to make it the default) write its
        absolute path to {DEFAULT_CONF_PATH}.
    """)
    response = input(f"\nDo you really want to edit the file ./{arg}? [y/N] ")
    if not response.casefold().startswith("y"):
        raise UsageError


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
        catch_usage_mistake(args.paths, prompt=not args.no_prompt)
    except UsageError:
        return 2
    try:
        editor = handle_editor_selection(provided_editor=args.editor)
    except EditorSelectionError:
        return 1
    exit_code = 0
    for path in args.paths:
        try:
            exit_code = run(
                path, editor, bgcolor=args.background, debug=args.debug, no_prompt=args.no_prompt
            )
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
