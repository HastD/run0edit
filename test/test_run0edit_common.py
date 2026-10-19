#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Unit tests for functions duplicated between run0edit_main.py and run0edit_inner.py
"""

import io
import os
import shutil
import unittest
from unittest import mock

import pytest

import run0edit_inner
import run0edit_main


class TestPrintErr(unittest.TestCase):
    """Tests for print_err"""

    def test_print_err(self):
        """Should output text to stderr with word wrapping"""
        MAX_WIDTH = 80
        text = "Lorem ipsum dolor sit amet " * 10
        for mod in (run0edit_inner, run0edit_main):
            with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                mod.print_err(text)
                output = mock_stderr.getvalue()
            assert output.startswith("run0edit: ")
            assert max(len(line) for line in output.split("\n")) <= MAX_WIDTH
            unwrapped = output.replace("\n", " ")
            assert unwrapped.removeprefix("run0edit: ").strip() == text.strip()

    def test_no_wrap(self):
        """Should output text to stderr without word wrapping"""
        text = "    " + "Lorem ipsum dolor sit amet " * 10
        for mod in (run0edit_inner, run0edit_main):
            with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                mod.print_err(text, wrap=False)
                output = mock_stderr.getvalue()
            assert output.rstrip("\n") == "run0edit: " + text.lstrip(" ")


class TestReadonlyFilesystem(unittest.TestCase):
    """Tests for readonly_filesystem"""

    def test_ro_path(self):
        """Should detect read-only filesystem"""
        path = mock.sentinel.path
        mock_statvfs_result = mock.NonCallableMock()
        mock_statvfs_result.f_flag = os.ST_RDONLY
        for mod in (run0edit_inner, run0edit_main):
            with mock.patch("os.statvfs") as mock_statvfs:
                mock_statvfs.return_value = mock_statvfs_result
                assert mod.readonly_filesystem(path)
                mock_statvfs.assert_called_once_with(path)

    def test_rw_path(self):
        """Should detect non-read-only filesystem"""
        for mod in (run0edit_inner, run0edit_main):
            assert not mod.readonly_filesystem("/var")

    def test_bad_path(self):
        """Should return None for nonexistent path"""
        for mod in (run0edit_inner, run0edit_main):
            assert mod.readonly_filesystem("/this/path/does/not/exist") is None


class TestFindCommand(unittest.TestCase):
    """Tests for find_command"""

    def test_finds_cmds(self):
        """Should find external commands used by module"""
        for mod in (run0edit_inner, run0edit_main):
            assert mod.find_command("chattr") == "/usr/bin/chattr"
            assert mod.find_command("lsattr") == "/usr/bin/lsattr"
            if shutil.which("run0"):  # pragma: no cover
                assert mod.find_command("run0") == "/usr/bin/run0"

    def test_nonexistent_cmd(self):
        """Should not find nonexistent command"""
        for mod in (run0edit_inner, run0edit_main):
            with pytest.raises(mod.CommandNotFoundError, match="this_cmd_does_not_exist"):
                mod.find_command("this_cmd_does_not_exist")

    def test_check_args(self):
        """Should pass correct arguments to shutil.which"""
        cmd = mock.sentinel.cmd
        for mod in (run0edit_inner, run0edit_main):
            with mock.patch("shutil.which") as mock_which:
                mod.find_command(cmd)
                mock_which.assert_called_once_with(cmd, path="/usr/bin:/bin:/usr/sbin:/sbin")
