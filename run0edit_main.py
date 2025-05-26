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
import shutil
import subprocess  # nosec
import sys
import textwrap
import tempfile

from typing import Final, Sequence

VERSION: Final[str] = "0.5.0"


def find_command(command: str) -> str | None:
    """Search for command using a default path."""
    return shutil.which(command, path=os.defpath)


def editor_path(
    *, conf_paths: Sequence[str] | None = None, fallbacks: Sequence[str] | None = None
) -> str | None:
    """Get path to editor executable."""
    is_rx = os.F_OK | os.R_OK | os.X_OK
    if conf_paths is None:
        conf_paths = ("/etc/run0edit/editor.conf", "/usr/etc/run0edit/editor.conf")
    for conf_path in conf_paths:
        try:
            with open(conf_path, "r", encoding="utf8") as f:
                editor = f.read().strip()
        except OSError:
            continue
        else:
            if os.path.isfile(editor) and os.access(editor, is_rx):
                return editor
    if fallbacks is None:
        fallbacks = ("nano", "vi")
    for fallback in fallbacks:
        editor = find_command(fallback)
        if editor is not None:
            return editor
    return None


def readonly_filesystem(path: str) -> bool | None:
    """Determine if the path is on a read-only filesystem."""
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return None


def make_temp_file(path: str) -> str:
    """Create a temporary file with a random suffix appended to the filename."""
    name = os.path.basename(path)
    return tempfile.mkstemp(prefix=f"{name:.64}.")[1]


def clean_temp_file(path: str, *, only_if_empty: bool = False):
    """Remove the temporary file (optionally only if empty)."""
    if not only_if_empty or os.path.getsize(path) == 0:
        os.remove(path)


# fmt: off
INNER_SCRIPT: Final[str] = r'''
{{ SCRIPT }}
'''
# fmt: on


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


def build_run0_arguments(
    path: str, temp_path: str, editor: str, *, debug: bool = False
) -> list[str]:
    """Construct the arguments to be passed to run0."""
    run0_cmd = find_command("run0")
    python_cmd = find_command("python3")
    if run0_cmd is None or python_cmd is None:
        raise RuntimeError("run0 or python3 command not found")
    args = [run0_cmd, f'--description=run0edit "{path}"']
    for systemd_property in SYSTEMD_SANDBOX_PROPERTIES:
        args.append(f"--property={systemd_property}")
    rw_path = sandbox_path(path)
    args += [
        f'--property=ReadWritePaths="{escape_path(rw_path)}" "{escape_path(temp_path)}"',
        python_cmd,
        "-c",
        INNER_SCRIPT,
        path,
        temp_path,
        editor,
    ]
    if debug:
        args.append("--debug")
    return args


def print_err(message: str):
    """Print error message to stderr with text wrapping."""
    print(textwrap.wrap(f"run0edit: {message}"), file=sys.stderr)


def run(path: str, editor: str, *, debug: bool = False) -> int:
    """Main program to run for a given file."""
    path = os.path.realpath(path)
    if os.path.isdir(path):
        print_err(f"{path} is a directory")
        return 1
    if os.path.isfile(path) and os.access(path, os.R_OK | os.W_OK):
        print_err(f"{path} is writable by the current user; run0edit is unnecessary.")
        return 1
    directory = os.path.dirname(path)
    readonly = readonly_filesystem(path)
    if readonly is None:
        readonly = readonly_filesystem(directory)
    if readonly:
        print_err(f"{path} is on a read-only filesystem.")
        return 1
    temp_filename = make_temp_file(path)
    run0_args = build_run0_arguments(path, temp_filename, editor, debug=debug)
    env = os.environb.copy()
    env[b"SYSTEMD_ADJUST_TERMINAL_TITLE"] = b"false"
    process = subprocess.run(run0_args, env=env, check=False)  # nosec
    match process.returncode:
        case 0:
            clean_temp_file(temp_filename)
            return 0
        case 226:
            print_err(f"invalid argument: directory {directory} does not exist")
            clean_temp_file(temp_filename)
            return 1
        case _:
            clean_temp_file(temp_filename, only_if_empty=True)
            return process.returncode


def main() -> int:
    """Main function. Return value becomes the exit code."""
    description = "run0edit allows a permitted user to edit a file as root."
    epilog = """\
    To use another text editor, write the path to your text editor of choice to
        /etc/run0edit/editor.conf"""
    parser = argparse.ArgumentParser(prog="run0edit", description=description, epilog=epilog)
    parser.add_argument("-v", "--version", action="version", version=f"run0edit {VERSION}")
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("paths", nargs="+", metavar="FILE", help="path to the file to be edited")
    args = parser.parse_args()
    editor = editor_path()
    if editor is None:
        print_err("""
            Editor not found. Please install either nano or vi, or write the path to
            the text editor of your choice to /etc/run0edit/editor.conf
        """)
        return 1
    exit_code = 0
    for path in args.paths:
        exit_code = run(path, editor, debug=args.debug)
        if exit_code != 0:
            break
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
