#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Integration tests for run0edit. Meant to run in a VM or container environment
with passwordless run0.
"""

import os
import pty
import re
import secrets
import subprocess
import sys
import tempfile
import termios
from typing import Final

RUN0: Final[str] = "/usr/bin/run0"
EDITED_TEXT: Final[str] = "~~~edited text~~~"
DEFAULT_EDITOR_CMD: Final[str] = f'echo "{EDITED_TEXT}" >"$1"'
WINDOW_SIZE: Final[tuple[int, int]] = (32, 100)


def cmd(name: str) -> str:
    """Absolute path to system binary"""
    return f"/usr/bin/{name}"


def parse_pty_output(data: bytes) -> str:
    """Clean initial ANSI control codes and normalize line breaks"""
    data = re.sub(rb"^\x1b\][^\x1b]*\x1b\\", b"", data)
    return data.decode().strip().replace("\r\n", "\n")


def run0edit(
    *args: str, editor_cmd: str = DEFAULT_EDITOR_CMD, check: bool = True
) -> tuple[int, str]:
    """Call run0edit with the provided arguments in a PTY, return the exit code and output"""
    try:
        editor_fd, editor = tempfile.mkstemp(prefix="run0edit-editor-", text=True)
        with os.fdopen(editor_fd, "w", encoding="utf8") as f:
            f.write("#!/bin/sh\n" + editor_cmd + "\n")
        os.chmod(editor, 0o700)

        cmd_args = [
            "./run0edit-local",
            f"--editor={editor}",
            "--background=",
            "--debug",
            "--no-prompt",
            "--",
            *args,
        ]
        pid, ptm = pty.fork()
        if pid == 0:
            os.execv("./run0edit-local", cmd_args)

        termios.tcsetwinsize(ptm, WINDOW_SIZE)
        output = b""
        try:
            while new_data := os.read(ptm, 1024):
                output += new_data
        except OSError:
            pass
        _, waitstatus = os.waitpid(pid, 0)
        status = os.waitstatus_to_exitcode(waitstatus)
        output = parse_pty_output(output)
        if check and status != 0:
            print(f"output:\n{output}\n", file=sys.stderr)
            raise RuntimeError
        return status, output
    finally:
        try:
            os.remove(editor)
        except OSError:
            pass


def random_filename(length: int = 32) -> str:
    """Generates a random string that can be used as a filename (without creating the file)."""
    return secrets.token_hex((length + 1) // 2)


class File:
    """A test file, possibly owned by root or immutable."""

    def __init__(
        self,
        directory: str | None = None,
        *,
        root_owned: bool = True,
        immutable: bool = False,
        create: bool = True,
        is_dir: bool = False,
        mode: int | None = None,
    ):
        if directory is None:
            directory = tempfile.gettempdir()
        if not create:
            self._path = f"{directory}/{random_filename()}"
            return
        cmd_args = [cmd("mktemp"), "-p", directory]
        if is_dir:
            cmd_args.append("-d")
        if root_owned:
            cmd_args = [RUN0, *cmd_args]
        result = subprocess.run(
            cmd_args,
            check=True,
            capture_output=True,
            text=True,
        )
        self._path = result.stdout.strip()
        if mode is not None:
            subprocess.run([RUN0, cmd("chmod"), f"{mode:o}", "--", self._path], check=True)
        if immutable:
            subprocess.run([RUN0, cmd("chattr"), "+i", "--", self._path], check=True)

    @property
    def path(self) -> str:
        """Get the path."""
        return self._path

    def is_immutable(self) -> bool:
        """Test if the file has the immutable attribute."""
        result = subprocess.run(
            [RUN0, cmd("lsattr"), "-d", "--", self._path],
            check=True,
            capture_output=True,
            text=True,
        )
        return "i" in result.stdout.strip().split(maxsplit=1)[0]

    def read(self) -> str:
        """Get the file's contents."""
        result = subprocess.run(
            [RUN0, cmd("cat"), "--", self._path],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def __del__(self):
        """Remove the file."""
        subprocess.run(
            [RUN0, cmd("chattr"), "-R", "-i", "--", self._path], check=False, capture_output=True
        )
        subprocess.run([RUN0, cmd("rm"), "-rf", "--", self._path], check=False, capture_output=True)


def test_edit_file():
    """Should successfully change the contents of a root-owned file"""
    file = File(directory="/root", root_owned=True)
    _, output = run0edit(file.path)
    assert output == ""
    assert file.read().strip() == EDITED_TEXT


def test_file_unchanged():
    """Should note that unchanged file is unchanged"""
    file = File(directory="/var", root_owned=True)
    _, output = run0edit(file.path, editor_cmd="true")
    assert output == f"run0edit: {file.path} unchanged"
    assert file.read().strip() == ""


def test_create_file():
    """Should successfully create a file in a root-owned directory"""
    file = File(directory="/var", create=False)
    _, output = run0edit(file.path)
    assert output == ""
    assert file.read().strip() == EDITED_TEXT


def test_not_created():
    """Should not create empty file"""
    file = File(directory="/var", create=False)
    _, output = run0edit(file.path, editor_cmd="true")
    assert output == f"run0edit: {file.path} not created"
    assert not os.path.exists(file.path)


def test_edit_immutable_file():
    """Should successfully change the contents of immutable file and restore the attribute"""
    file = File(root_owned=False, immutable=True)
    _, output = run0edit(file.path)
    assert output == "Immutable attribute reapplied."
    assert file.read().strip() == EDITED_TEXT
    assert file.is_immutable()


def test_immutable_file_unchanged():
    """Should not touch immutable flag on unchanged immutable file"""
    file = File(root_owned=False, immutable=True)
    _, output = run0edit(file.path, editor_cmd="true")
    assert output == f"run0edit: {file.path} unchanged"
    assert file.read().strip() == ""


def test_create_file_in_immutable_directory():
    """Should successfully create new file in immutable directory"""
    directory = File(root_owned=False, immutable=True, is_dir=True)
    file = File(directory=directory.path, create=False)
    _, output = run0edit(file.path)
    assert output == "Immutable attribute reapplied."
    assert file.read().strip() == EDITED_TEXT
    assert directory.is_immutable()
    assert file.is_immutable()


def test_create_file_in_unreadable_directory():
    """Should successfully create new file in directory not readable by user"""
    directory = File(is_dir=True, mode=0o700)
    file = File(directory=directory.path, create=False)
    _, output = run0edit(file.path)
    assert output == ""
    assert file.read().strip() == EDITED_TEXT


def test_user_writable_file():
    """Should give expected error if file is user-writable"""
    file = File(root_owned=False)
    status, output = run0edit(file.path, check=False)
    assert status == 1
    assert " is writable by the current user; run0edit is unnecessary." in output.replace("\n", " ")
    assert file.read().strip() == ""


def test_read_only_filesystem():
    """Should give expected error if file is on read-only filesystem"""
    ro_mount_dir = tempfile.mkdtemp()
    subprocess.run(
        [
            RUN0,
            "--via-shell",
            "mount",
            "--bind",
            "-o",
            "ro",
            tempfile.gettempdir(),
            ro_mount_dir,
        ],
        check=True,
    )
    file = File(directory=ro_mount_dir, create=False)
    status, output = run0edit(file.path, check=False)
    assert status == 1
    assert (
        output.strip().replace("\n", " ") == f"run0edit: {file.path} is on a read-only filesystem."
    )
    subprocess.run([RUN0, cmd("umount"), ro_mount_dir], check=True)
    os.rmdir(ro_mount_dir)


def test_editor_fails():
    """Should give expected error if editor fails"""
    file = File(directory="/var", root_owned=True)
    status, output = run0edit(file.path, editor_cmd="false", check=False)
    assert status == 1
    assert output.startswith("run0edit: failed to edit temporary file at ")
    assert file.read().strip() == ""


def test_editor_runs_unprivileged():
    """Editor should run with the unprivileged user's UID and GID"""
    file = File(directory="/root", root_owned=True)
    editor_cmd = r"""
    printf 'uid=%s, euid=%s, gid=%s, egid=%s, groups=%s\n' \
        "$(id -ru)" "$(id -u)" "$(id -rg)" "$(id -g)" "$(id -G)" \
        >"$1"
    """
    run0edit(file.path, editor_cmd=editor_cmd)
    uid = os.getuid()
    gid = os.getgid()
    assert file.read().strip() == f"uid={uid}, euid={uid}, gid={gid}, egid={gid}, groups={gid}"


def test_nnp_bit_set():
    """Editor should run with no_new_privs bit set"""
    file = File(directory="/root", root_owned=True)
    run0edit(file.path, editor_cmd='setpriv --dump >"$1"')
    assert re.search(r"^no_new_privs:\s+1$", file.read(), re.MULTILINE)


def test_pdeathsig_set():
    """Editor should have parent death signal set to SIGHUP"""
    file = File(directory="/root", root_owned=True)
    _, output = run0edit(file.path, editor_cmd="exec setpriv --dump")
    assert re.search(r"^Parent death signal:\s+HUP$", output, re.MULTILINE)


def test_capabilities_dropped():
    """Editor should run with no capabilities"""
    file = File(directory="/root", root_owned=True)
    run0edit(file.path, editor_cmd='/usr/sbin/capsh --print >"$1"')
    assert re.search(r"^Current:\s+=$", file.read(), re.MULTILINE)
    assert re.search(r"^Ambient set\s+=$", file.read(), re.MULTILINE)


def test_window_size():
    """Editor terminal should be sized to match the window"""
    file = File(directory="/root", root_owned=True)
    editor_cmd = 'sleep 0.5; printf "lines=%s, cols=%s\n" "$(tput lines)" "$(tput cols)" >"$1"'
    run0edit(file.path, editor_cmd=editor_cmd)
    lines, columns = WINDOW_SIZE
    assert file.read().strip() == f"lines={lines}, cols={columns}"
