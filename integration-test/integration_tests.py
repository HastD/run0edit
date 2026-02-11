#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Integration tests for run0edit. Meant to run in a VM or container environment
with passwordless run0.
"""

import os
import secrets
import subprocess  # nosec
import tempfile
import unittest
from typing import Final

RUN0: Final[str] = "/usr/bin/run0"
EDITOR: Final[str] = os.path.realpath("./integration-test/mock-editor.sh")
EDITED_TEXT: Final[str] = "~~~edited text~~~"


def cmd(name: str) -> str:
    """Absolute path to system binary"""
    return f"/usr/bin/{name}"


def run0edit(
    *args: str, editor: str = EDITOR, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Call run0edit with the provided arguments"""
    return subprocess.run(
        ["./run0edit-local", f"--editor={editor}", "--debug", "--no-prompt", "--", *args],
        check=check,
        capture_output=True,
        text=True,
    )  # nosec


def random_filename(length: int = 32) -> str:
    """Generates a random string that can be used as a filename (without creating the file)."""
    return secrets.token_hex((length + 1) // 2)


class TestFile:
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
        )  # nosec
        self._path = result.stdout.strip()
        if mode is not None:
            subprocess.run([RUN0, cmd("chmod"), f"{mode:o}", "--", self._path], check=True)  # nosec
        if immutable:
            subprocess.run([RUN0, cmd("chattr"), "+i", "--", self._path], check=True)  # nosec

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
        )  # nosec
        return "i" in result.stdout.strip().split(maxsplit=1)[0]

    def read(self) -> str:
        """Get the file's contents."""
        result = subprocess.run(
            [RUN0, cmd("cat"), "--", self._path],
            check=True,
            capture_output=True,
            text=True,
        )  # nosec
        return result.stdout

    def __del__(self):
        """Remove the file."""
        subprocess.run(
            [RUN0, cmd("chattr"), "-R", "-i", "--", self._path], check=False, capture_output=True
        )  # nosec
        subprocess.run([RUN0, cmd("rm"), "-rf", "--", self._path], check=False, capture_output=True)  # nosec


class TestIntegration(unittest.TestCase):
    """Integration tests"""

    def test_edit_file(self):
        """Should successfully change the contents of a root-owned file"""
        file = TestFile(directory="/root", root_owned=True)
        result = run0edit(file.path)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertEqual(file.read().strip(), EDITED_TEXT)

    def test_file_unchanged(self):
        """Should note that unchanged file is unchanged"""
        file = TestFile(directory="/var", root_owned=True)
        result = run0edit(file.path, editor=cmd("true"))
        self.assertEqual(result.stdout, f"run0edit: {file.path} unchanged\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(file.read().strip(), "")

    def test_create_file(self):
        """Should successfully create a file in a root-owned directory"""
        file = TestFile(directory="/var", create=False)
        result = run0edit(file.path)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")
        self.assertEqual(file.read().strip(), EDITED_TEXT)

    def test_not_created(self):
        """Should not create empty file"""
        file = TestFile(directory="/var", create=False)
        result = run0edit(file.path, editor=cmd("true"))
        self.assertEqual(result.stdout, f"run0edit: {file.path} not created\n")
        self.assertEqual(result.stderr, "")
        self.assertFalse(os.path.exists(file.path))

    def test_edit_immutable_file(self):
        """Should successfully change the contents of immutable file and restore the attribute"""
        file = TestFile(root_owned=False, immutable=True)
        result = run0edit(file.path)
        self.assertEqual(result.stdout.strip(), "Immutable attribute reapplied.")
        self.assertEqual(result.stderr, "")
        self.assertEqual(file.read().strip(), EDITED_TEXT)
        self.assertTrue(file.is_immutable())

    def test_immutable_file_unchanged(self):
        """Should not touch immutable flag on unchanged immutable file"""
        file = TestFile(root_owned=False, immutable=True)
        result = run0edit(file.path, editor=cmd("true"))
        self.assertEqual(result.stdout, f"run0edit: {file.path} unchanged\n")
        self.assertEqual(result.stderr, "")
        self.assertEqual(file.read().strip(), "")

    def test_create_file_in_immutable_directory(self):
        """Should successfully create new file in immutable directory"""
        directory = TestFile(root_owned=False, immutable=True, is_dir=True)
        file = TestFile(directory=directory.path, create=False)
        result = run0edit(file.path)
        self.assertEqual(result.stdout.strip(), "Immutable attribute reapplied.")
        self.assertEqual(result.stderr, "")
        self.assertEqual(file.read().strip(), EDITED_TEXT)
        self.assertTrue(directory.is_immutable())
        self.assertFalse(file.is_immutable())

    def test_create_file_in_unreadable_directory(self):
        """Should successfully create new file in directory not readable by user"""
        directory = TestFile(is_dir=True, mode=0o700)
        file = TestFile(directory=directory.path, create=False)
        result = run0edit(file.path)
        self.assertEqual(result.stdout.strip(), "")
        self.assertEqual(result.stderr, "")
        self.assertEqual(file.read().strip(), EDITED_TEXT)

    def test_user_writable_file(self):
        """Should give expected error if file is user-writable"""
        file = TestFile(root_owned=False)
        result = run0edit(file.path, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn(
            " is writable by the current user; run0edit is unnecessary.",
            result.stderr.replace("\n", " "),
        )
        self.assertEqual(file.read().strip(), "")

    def test_read_only_filesystem(self):
        """Should give expected error if file is on read-only filesystem"""
        ro_mount_dir = tempfile.mkdtemp()
        mount_ro = 'mount --bind -o ro "$1" "$2"'
        subprocess.run(
            [RUN0, cmd("sh"), "-c", mount_ro, cmd("sh"), tempfile.gettempdir(), ro_mount_dir],
            check=True,
        )
        file = TestFile(directory=ro_mount_dir, create=False)
        result = run0edit(file.path, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertEqual(
            result.stderr.strip().replace("\n", " "),
            f"run0edit: {file.path} is on a read-only filesystem.",
        )
        subprocess.run([RUN0, cmd("umount"), ro_mount_dir], check=True)
        os.rmdir(ro_mount_dir)

    def test_editor_fails(self):
        """Should give expected error if editor fails"""
        file = TestFile(directory="/var", root_owned=True)
        result = run0edit(file.path, editor=cmd("false"), check=False)
        self.assertEqual(result.returncode, 1)
        self.assertRegex(result.stdout, "^run0edit: failed to edit temporary file at ")
        self.assertEqual(file.read().strip(), "")


if __name__ == "__main__":
    unittest.main()
