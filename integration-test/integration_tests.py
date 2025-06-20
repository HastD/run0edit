#!/usr/bin/env python3

"""
Integration tests for run0edit. Meant to run in a VM or container environment
with passwordless run0.
"""

import os
import subprocess  # nosec
import unittest
from typing import Final, Union

RUN0: Final[str] = "/usr/bin/run0"
EDITOR: Final[str] = os.path.realpath("./integration-test/mock-editor.sh")
EDITED_TEXT: Final[str] = "~~~edited text~~~"


def cmd(name: str) -> str:
    """Absolute path to system binary"""
    return f"/usr/bin/{name}"


def run0edit(*args: str) -> None:
    """Call run0edit with the provided arguments"""
    subprocess.run(
        ["./run0edit-local", f"--editor={EDITOR}", "--no-prompt", "--", *args], check=True
    )  # nosec


class TestFile:
    """A test file, possibly owned by root or immutable."""

    def __init__(
        self,
        directory: Union[str, None] = None,
        *,
        root_owned: bool = True,
        immutable: bool = False,
    ):
        cmd_args = [cmd("mktemp")]
        if directory is not None:
            cmd_args += ["-p", directory]
        if root_owned:
            cmd_args = [RUN0, *cmd_args]
        result = subprocess.run(
            cmd_args,
            check=True,
            capture_output=True,
            text=True,
        )  # nosec
        self._path = result.stdout.strip()
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
        subprocess.run([RUN0, cmd("chattr"), "-i", "--", self._path], check=False)  # nosec
        subprocess.run([RUN0, cmd("rm"), "--", self._path], check=False)  # nosec


class TestIntegration(unittest.TestCase):
    """Integration tests"""

    def test_edit_file(self):
        """Should successfully change the contents of a root-owned file"""
        file = TestFile(directory="/root", root_owned=True)
        run0edit(file.path)
        self.assertEqual(file.read().strip(), EDITED_TEXT)

    def test_edit_immutable_file(self):
        """Should successfully change the contents of immutable file and restore the attribute"""
        file = TestFile(root_owned=False, immutable=True)
        run0edit(file.path)
        self.assertEqual(file.read().strip(), EDITED_TEXT)
        self.assertTrue(file.is_immutable())


if __name__ == "__main__":
    unittest.main()
