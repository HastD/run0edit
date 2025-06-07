#!/usr/bin/env python3

"""
Unit tests for functions duplicated between run0edit_main.py and run0edit_inner.py
"""

import os
import shutil
import unittest
from unittest import mock

import run0edit_inner
import run0edit_main


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
                self.assertTrue(mod.readonly_filesystem(path))
                self.assertEqual(mock_statvfs.call_args.args, (path,))

    def test_rw_path(self):
        """Should detect non-read-only filesystem"""
        for mod in (run0edit_inner, run0edit_main):
            self.assertFalse(mod.readonly_filesystem("/var"))

    def test_bad_path(self):
        """Should return None for nonexistent path"""
        for mod in (run0edit_inner, run0edit_main):
            self.assertIsNone(mod.readonly_filesystem("/this/path/does/not/exist"))


class TestFindCommand(unittest.TestCase):
    """Tests for find_command"""

    def test_finds_cmds(self):
        """Should find external commands used by module"""
        for mod in (run0edit_inner, run0edit_main):
            self.assertEqual(mod.find_command("chattr"), "/usr/bin/chattr")
            self.assertEqual(mod.find_command("lsattr"), "/usr/bin/lsattr")
            if shutil.which("run0"):  # pragma: no cover
                self.assertEqual(mod.find_command("run0"), "/usr/bin/run0")

    def test_nonexistent_cmd(self):
        """Should not find nonexistent command"""
        for mod in (run0edit_inner, run0edit_main):
            with self.assertRaisesRegex(mod.CommandNotFoundError, "this_cmd_does_not_exist"):
                mod.find_command("this_cmd_does_not_exist")

    def test_check_args(self):
        """Should pass correct arguments to shutil.which"""
        cmd = mock.sentinel.cmd
        for mod in (run0edit_inner, run0edit_main):
            with mock.patch("shutil.which") as mock_which:
                mod.find_command(cmd)
                self.assertEqual(mock_which.call_args_list, [((cmd,), {"path": "/usr/bin:/bin"})])
