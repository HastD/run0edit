#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Unit tests for run0edit_inner.py"""

import io
import os
import unittest
from unittest import mock

import run0edit_inner as inner

from . import new_test_dir, new_test_file, remove_test_dir, remove_test_file


class TestRunCommand(unittest.TestCase):
    """Tests for run_command"""

    def test_echo(self):
        """Should get correct output from echo"""
        out = inner.run_command("echo", "test", capture_output=True)
        self.assertEqual(out, "test\n")

    def test_not_shell(self):
        """Command should not be run as a shell"""
        out = inner.run_command("echo", ";", "echo", "foo", capture_output=True)
        self.assertEqual(out, "; echo foo\n")

    def test_not_captured(self):
        """Should get no output if not captured"""
        self.assertIsNone(inner.run_command("true"))

    def test_cmd_not_found(self):
        """Running nonexistent command should raise correct error"""
        with self.assertRaises(inner.CommandNotFoundError):
            inner.run_command("this_cmd_does_not_exist")

    def test_cmd_fails(self):
        """Failed command should raise correct error"""
        with self.assertRaises(inner.SubprocessError):
            inner.run_command("false")


@mock.patch("sys.stdout", new_callable=io.StringIO)
class TestCheckFileExists(unittest.TestCase):
    """Tests for check_file_exists"""

    def setUp(self):
        """Make test directory and test file"""
        self.dir = new_test_dir()
        self.file = new_test_file()

    def tearDown(self):
        """Remove test directory and test file"""
        remove_test_dir(self.dir)
        remove_test_file(self.file)

    def test_regular_file(self, mock_stdout):
        """Should return True for regular file"""
        self.assertTrue(inner.check_file_exists(self.file))
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_directory(self, mock_stdout):
        """Should raise NotRegularFileError for symlink to directory"""
        with self.assertRaises(inner.NotRegularFileError):
            inner.check_file_exists(self.dir)
        self.assertEqual(mock_stdout.getvalue(), "run0edit: invalid argument: not a regular file\n")

    def test_symlink_file(self, mock_stdout):
        """Should raise NotRegularFileError for symlink to file"""
        symlink = f"{self.file}-link"
        os.symlink(self.file, symlink)
        with self.assertRaises(inner.NotRegularFileError):
            inner.check_file_exists(symlink)
        self.assertEqual(mock_stdout.getvalue(), "run0edit: invalid argument: not a regular file\n")
        os.remove(symlink)

    def test_symlink_dir(self, mock_stdout):
        """Should raise NotRegularFileError for symlink to directory"""
        symlink = f"{self.dir}-link"
        os.symlink(self.dir, symlink)
        with self.assertRaises(inner.NotRegularFileError):
            inner.check_file_exists(symlink)
        self.assertEqual(mock_stdout.getvalue(), "run0edit: invalid argument: not a regular file\n")
        os.remove(symlink)

    def test_dev_file(self, mock_stdout):
        """Should raise NotRegularFileError for device file"""
        with self.assertRaises(inner.NotRegularFileError):
            inner.check_file_exists("/dev/null")
        self.assertEqual(mock_stdout.getvalue(), "run0edit: invalid argument: not a regular file\n")

    def test_no_file(self, mock_stdout):
        """Should return false if file does not exist and parent is directory"""
        file = f"{self.dir}/foo.txt"
        self.assertFalse(inner.check_file_exists(file))
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_no_directory(self, mock_stdout):
        """Should raise NoDirectoryError if parent directory does not exist"""
        with self.assertRaisesRegex(inner.NoDirectoryError, " does not exist"):
            inner.check_file_exists(os.path.join(self.dir, "foo/bar.txt"))
        self.assertEqual(
            mock_stdout.getvalue(), "run0edit: invalid argument: directory does not exist\n"
        )

    def test_bad_directory(self, mock_stdout):
        """Should raise NoDirectoryError if parent path is a file"""
        with self.assertRaisesRegex(inner.NoDirectoryError, " is not a directory"):
            inner.check_file_exists(os.path.join(self.file, "foo.txt"))
        self.assertEqual(
            mock_stdout.getvalue(), "run0edit: invalid argument: directory does not exist\n"
        )


class TestIsImmutable(unittest.TestCase):
    """Tests for is_immutable"""

    def test_mutable(self):
        """Non-immutable path"""
        self.assertFalse(inner.is_immutable("/var"))

    @mock.patch("run0edit_inner.run_command")
    def test_immutable_path(self, mock_run_command):
        """Test lsattr output parsed correctly when immutable"""
        path = "foo/bar"
        mock_run_command.return_value = f"--i-- {path}"
        self.assertTrue(inner.is_immutable(path))
        lsattr_args = mock_run_command.call_args
        self.assertEqual(lsattr_args.args[:2], ("lsattr", "-d"))
        self.assertEqual(lsattr_args.args[-1], path)
        self.assertTrue(lsattr_args.kwargs.get("capture_output"))

    @mock.patch("run0edit_inner.run_command")
    def test_i_in_filename(self, mock_run_command):
        """Test lsattr output parsed correctly when 'i' in filename"""
        path = "filename/with/letter/i"
        mock_run_command.return_value = f"----- {path}"
        self.assertFalse(inner.is_immutable(path))

    def test_bad_path(self):
        """Non-immutable directory"""
        self.assertFalse(inner.is_immutable("/this/path/does/not/exist"))


@mock.patch("run0edit_inner.input", create=True)
@mock.patch("sys.stdout", new_callable=io.StringIO)
class TestShouldRemoveImmutable(unittest.TestCase):
    """Tests for should_remove_immutable"""

    def test_dir(self, mock_stdout, mock_input):
        """Test answer on directory"""
        path = "/etc"
        inner.should_remove_immutable(path, is_dir=True)
        self.assertIn(path, mock_stdout.getvalue())
        self.assertIn("directory", mock_input.call_args.args[0])

    def test_not_dir(self, mock_stdout, mock_input):
        """Test answer on non-directory"""
        path = "/etc/hosts"
        inner.should_remove_immutable(path, is_dir=False)
        self.assertIn(path, mock_stdout.getvalue())
        self.assertNotIn("directory", mock_input.call_args.args[0])

    def test_answers(self, _, mock_input):
        """Test answer 'y'"""
        answers = ["y", "n", "", ".yes", "Y", "N", "YNO", "yyes", "nyan"]
        mock_input.side_effect = answers
        path = "/etc"
        for answer in answers:
            result = inner.should_remove_immutable(path, is_dir=True)
            self.assertEqual(result, answer.casefold().startswith("y"))


class TestCaseWithFiles(unittest.TestCase):
    """Base class for test cases with temp files automatically set up"""

    def setUp(self):
        """Set up test files"""
        self.file_contents = b"file contents"
        self.temp_contents = b"temp contents"
        self.filename = new_test_file(self.file_contents)
        self.temp_filename = new_test_file(self.temp_contents)
        self.new_filename = f"{self.temp_filename}-new"
        self.new_dir = os.path.dirname(self.new_filename)

    def tearDown(self):
        """Clean up test files"""
        remove_test_file(self.filename)
        remove_test_file(self.temp_filename)
        remove_test_file(self.new_filename)


class TestCheckReadonly(unittest.TestCase):
    """Tests for check_readonly"""

    RO_FILE: str = "/proc/version"
    RO_DIR: str = "/proc"

    def test_writable_file(self):
        """Should return False for writable file"""
        file = new_test_file()
        self.assertFalse(inner.check_readonly(file, is_dir=False))
        remove_test_file(file)

    def test_writable_dir(self):
        """Should return False for writable directory"""
        directory = new_test_dir()
        self.assertFalse(inner.check_readonly(directory, is_dir=True))
        remove_test_dir(directory)

    @mock.patch("run0edit_inner.readonly_filesystem")
    def test_ro_fs(self, mock_ro_fs):
        """Path on read-only filesystem should raise correct error"""
        mock_ro_fs.return_value = True
        with self.assertRaises(inner.ReadOnlyFilesystemError):
            inner.check_readonly(self.RO_FILE, is_dir=False)

    @mock.patch("run0edit_inner.is_immutable")
    @mock.patch("run0edit_inner.should_remove_immutable")
    def test_immutable_with_prompt(self, mock_should_remove_immutable, mock_is_immutable):
        """
        Should ask user if immutable and prompt=True, and should raise correct
        error if user answers no.
        """
        mock_is_immutable.return_value = True
        mock_should_remove_immutable.side_effect = [True, False]
        self.assertTrue(inner.check_readonly(self.RO_DIR, is_dir=True))
        with self.assertRaises(inner.ReadOnlyImmutableError):
            inner.check_readonly(self.RO_DIR, is_dir=True)
        self.assertTrue(mock_should_remove_immutable.called)

    @mock.patch("run0edit_inner.is_immutable")
    @mock.patch("run0edit_inner.should_remove_immutable")
    def test_immutable_no_prompt(self, mock_should_remove_immutable, mock_is_immutable):
        """Should not ask user if immutable and prompt=False"""
        mock_is_immutable.return_value = True
        self.assertTrue(inner.check_readonly(self.RO_DIR, is_dir=True, prompt_immutable=False))
        self.assertFalse(mock_should_remove_immutable.called)

    def test_ro_other(self):
        """Should raise expected error in other case"""
        with self.assertRaises(inner.ReadOnlyOtherError):
            inner.check_readonly(self.RO_DIR, is_dir=True)


@mock.patch("run0edit_inner.check_readonly")
class TestHandleCheckReadonly(TestCaseWithFiles):
    """Tests for handle_check_readonly"""

    def test_check_args(self, mock_check_ro):
        """Should pass expected arguments to check_readonly"""
        sent = mock.sentinel
        inner.handle_check_readonly(sent.path, is_dir=sent.is_dir, prompt_immutable=sent.prompt)
        self.assertEqual(mock_check_ro.call_args.args, (sent.path,))
        self.assertEqual(
            mock_check_ro.call_args.kwargs, {"is_dir": sent.is_dir, "prompt_immutable": sent.prompt}
        )

    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_error_messages(self, mock_stdout, mock_check_ro):
        """Should print appropriate error messages and re-raise exceptions"""
        errors: dict[type[inner.Run0editError], str] = {
            inner.ReadOnlyFilesystemError: "read-only filesystem",
            inner.ReadOnlyImmutableError: "user declined to remove immutable",
            inner.ReadOnlyOtherError: "is read-only",
        }
        mock_check_ro.side_effect = iter(errors)
        for exc, message in errors.items():
            with self.assertRaises(exc):
                inner.handle_check_readonly("foo", False)
            self.assertIn(message, mock_stdout.getvalue())
            mock_stdout.truncate(0)
            mock_stdout.seek(0)


class TestCopyFileContents(TestCaseWithFiles):
    """Tests for copy_file_contents"""

    def test_copy(self):
        """Should copy file contents when src and dest both exist and create=False"""
        inner.copy_file_contents(self.filename, self.temp_filename, create=False)
        with open(self.filename, "rb") as f_src, open(self.temp_filename, "rb") as f_dest:
            self.assertEqual(f_src.read(), self.file_contents)
            self.assertEqual(f_dest.read(), self.file_contents)

    def test_missing_src(self):
        """Should raise expected error when src does not exist"""
        with self.assertRaises(inner.FileCopyError):
            inner.copy_file_contents(self.new_filename, self.temp_filename, create=False)
        with self.assertRaises(inner.FileCopyError):
            inner.copy_file_contents(self.new_filename, self.temp_filename, create=True)

    def test_create_false_fails(self):
        """Should raise expected error when dest does not exist and create=False"""
        with self.assertRaises(inner.FileCopyError):
            inner.copy_file_contents(self.temp_filename, self.new_filename, create=False)

    def test_present_dest_fails(self):
        """Should raise expected error when dest exists and create=True"""
        with self.assertRaises(inner.FileCopyError):
            inner.copy_file_contents(self.temp_filename, self.filename, create=True)


@mock.patch("run0edit_inner.run_command")
class TestRunChattr(unittest.TestCase):
    """Tests for run_chattr"""

    def test_runs_command(self, mock_run_command):
        """Should run command with right args"""
        attr = mock.sentinel.attr
        path = mock.sentinel.path
        inner.run_chattr(attr, path)
        self.assertEqual(mock_run_command.call_args.args, ("chattr", attr, "--", path))

    def test_failed_chattr(self, mock_run_command):
        """Should raise ChattrError if chattr command fails"""
        mock_run_command.side_effect = [inner.CommandNotFoundError, inner.SubprocessError]
        with self.assertRaises(inner.ChattrError):
            inner.run_chattr("+i", "foo/bar")
        with self.assertRaises(inner.ChattrError):
            inner.run_chattr("+i", "foo/bar")


@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_inner.run_chattr")
class TestCopyToImmutableOriginal(TestCaseWithFiles):
    """Tests for copy_to_immutable_original"""

    def test_file_exists_immutable(self, mock_chattr, mock_stdout):
        """Should chattr and copy to original if file exists and is immutable"""
        inner.copy_to_immutable_original(
            self.filename, self.temp_filename, original_file_exists=True
        )
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertEqual(
            mock_chattr.call_args_list, [(("-i", self.filename),), (("+i", self.filename),)]
        )
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    def test_new_file_immutable(self, mock_chattr, mock_stdout):
        """Should chattr and copy to new file if directory is immutable"""
        inner.copy_to_immutable_original(
            self.new_filename, self.temp_filename, original_file_exists=False
        )
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        chattr_path = os.path.dirname(self.filename)
        self.assertEqual(
            mock_chattr.call_args_list, [(("-i", chattr_path),), (("+i", chattr_path),)]
        )
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("run0edit_inner.copy_file_contents")
    def test_reapply_chattr_if_error(self, mock_copy, mock_chattr, mock_stdout):
        """Should chattr +i even if copy fails"""
        mock_copy.side_effect = [inner.FileCopyError]
        with self.assertRaises(inner.FileCopyError):
            inner.copy_to_immutable_original(
                self.filename, self.temp_filename, original_file_exists=True
            )
        self.assertEqual(
            mock_chattr.call_args_list, [(("-i", self.filename),), (("+i", self.filename),)]
        )
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("run0edit_inner.copy_file_contents")
    def test_detect_file_contents_mismatch(self, mock_copy, mock_chattr, mock_stdout):
        """Should detect mismatch in file contents after reapplying +i"""
        mock_copy.side_effect = None
        with self.assertRaises(inner.FileContentsMismatchError):
            inner.copy_to_immutable_original(
                self.filename, self.temp_filename, original_file_exists=True
            )
        self.assertEqual(
            mock_chattr.call_args_list, [(("-i", self.filename),), (("+i", self.filename),)]
        )
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("filecmp.cmp")
    def test_immutable_failed_cmp_raises_error(self, mock_cmp, mock_chattr, mock_stdout):
        """File contents mismatch should trigger error"""
        mock_cmp.side_effect = [False, FileNotFoundError]
        for _ in range(2):
            with self.assertRaises(inner.FileContentsMismatchError):
                inner.copy_to_immutable_original(
                    self.filename, self.temp_filename, original_file_exists=True
                )
        self.assertEqual(
            mock_chattr.call_args_list, [(("-i", self.filename),), (("+i", self.filename),)] * 2
        )
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n" * 2)
        self.assertEqual(mock_cmp.call_args.args, (self.temp_filename, self.filename))


class TestShouldCopyToOriginal(TestCaseWithFiles):
    """Tests for should_copy_to_original"""

    def test_edited_temp_file(self):
        """Should return True if temp file differs from original file"""
        self.assertTrue(
            inner.should_copy_to_original(
                self.filename, self.temp_filename, original_file_exists=True
            )
        )

    def test_unchanged_temp_file(self):
        """Should return False if temp file has same contents as original file"""
        with open(self.filename, "rb") as f_file, open(self.temp_filename, "wb") as f_temp:
            f_temp.write(f_file.read())
        self.assertFalse(
            inner.should_copy_to_original(
                self.filename, self.temp_filename, original_file_exists=True
            )
        )

    def test_new_nonempty_temp_file(self):
        """Should return True if original file does not exist and temp file is non-empty"""
        self.assertTrue(
            inner.should_copy_to_original(
                self.new_filename, self.temp_filename, original_file_exists=False
            )
        )

    def test_new_empty_temp_file(self):
        """Should return False if original file does not exist and temp file is empty"""
        with open(self.temp_filename, "wb"):
            pass
        self.assertFalse(
            inner.should_copy_to_original(
                self.new_filename, self.temp_filename, original_file_exists=False
            )
        )


@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_inner.run_chattr")
class TestHandleCopyToOriginal(TestCaseWithFiles):
    """Tests for handle_copy_to_original"""

    def test_file_edited(self, mock_chattr, mock_stdout):
        """Should copy if temp file differs from original file"""
        inner.handle_copy_to_original(
            self.filename, self.temp_filename, original_file_exists=True, immutable=False
        )
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertFalse(mock_chattr.called)
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_file_edited_immutable(self, mock_chattr, mock_stdout):
        """Should copy and chattr if temp file differs from original immutable file"""
        inner.handle_copy_to_original(
            self.filename, self.temp_filename, original_file_exists=True, immutable=True
        )
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertEqual(
            mock_chattr.call_args_list, [(("-i", self.filename),), (("+i", self.filename),)]
        )
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("run0edit_inner.copy_to_immutable_original")
    def test_file_unchanged(self, mock_copy_to_orig, mock_chattr, mock_stdout):
        """Should not copy if temp file has same contents as original file"""
        with open(self.filename, "rb") as f_file, open(self.temp_filename, "wb") as f_temp:
            f_temp.write(f_file.read())
        inner.handle_copy_to_original(
            self.filename, self.temp_filename, original_file_exists=True, immutable=True
        )
        self.assertFalse(mock_copy_to_orig.called)
        self.assertFalse(mock_chattr.called)
        self.assertIn("unchanged", mock_stdout.getvalue())

    def test_file_created(self, mock_chattr, mock_stdout):
        """Should copy to new file if temp file is non-empty"""
        inner.handle_copy_to_original(
            self.new_filename, self.temp_filename, original_file_exists=False, immutable=False
        )
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertFalse(mock_chattr.called)
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_file_created_immutable(self, mock_chattr, mock_stdout):
        """Should chattr directory and copy to new file if temp file is non-empty"""
        inner.handle_copy_to_original(
            self.new_filename, self.temp_filename, original_file_exists=False, immutable=True
        )
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertEqual(
            mock_chattr.call_args_list, [(("-i", self.new_dir),), (("+i", self.new_dir),)]
        )
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("run0edit_inner.copy_to_original")
    def test_file_not_created_empty(self, mock_copy, mock_chattr, mock_stdout):
        """Should not create new file if temp file is empty"""
        with open(self.temp_filename, "wb"):
            pass
        inner.handle_copy_to_original(
            self.new_filename, self.temp_filename, original_file_exists=False, immutable=True
        )
        self.assertFalse(mock_copy.called)
        self.assertFalse(mock_chattr.called)
        self.assertIn("not created", mock_stdout.getvalue())

    @mock.patch("run0edit_inner.copy_to_original")
    def test_error_messages(self, mock_copy, mock_chattr, mock_stdout):
        """Should print appropriate error messages and re-raise exceptions"""
        errors: dict[type[inner.Run0editError], str] = {
            inner.FileCopyError: "unable to copy contents of temporary file",
            inner.ChattrError: "failed to run chattr",
            inner.FileContentsMismatchError: "does not match contents of edited tempfile",
        }
        mock_copy.side_effect = iter(errors)
        for exc, message in errors.items():
            with self.assertRaises(exc):
                inner.handle_copy_to_original(
                    self.filename, self.temp_filename, original_file_exists=True, immutable=False
                )
            self.assertIn(message, mock_stdout.getvalue())
            mock_stdout.truncate(0)
            mock_stdout.seek(0)
        self.assertFalse(mock_chattr.called)


@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_inner.run_command")
class TestRunEditor(unittest.TestCase):
    """Tests for run_editor"""

    @mock.patch("run0edit_inner.find_command")
    def test_check_args(self, mock_find_cmd, mock_run_cmd, mock_stdout):
        """Should pass correct arguments to run_command"""
        editor = mock.sentinel.editor
        path = mock.sentinel.path
        mock_find_cmd.side_effect = lambda cmd: f"/bin/{cmd}"
        inner.run_editor(uid=42, editor=editor, path=path)
        self.assertEqual(
            mock_run_cmd.call_args.args,
            ("run0", "--user=42", "--", "/bin/sh", "-c", '"$1" "$2"', "/bin/sh", editor, path),
        )
        self.assertEqual(mock_stdout.getvalue(), "")

    @mock.patch("run0edit_inner.find_command")
    def test_check_args_with_bgcolor(self, mock_find_cmd, mock_run_cmd, mock_stdout):
        """Should pass correct arguments to run_command"""
        editor = mock.sentinel.editor
        path = mock.sentinel.path
        bgcolor = "bgcolor"
        mock_find_cmd.side_effect = lambda cmd: f"/bin/{cmd}"
        inner.run_editor(uid=42, editor=editor, path=path, bgcolor=bgcolor)
        self.assertEqual(
            mock_run_cmd.call_args.args,
            (
                "run0",
                "--user=42",
                "--background=bgcolor",
                "--",
                "/bin/sh",
                "-c",
                '"$1" "$2"',
                "/bin/sh",
                editor,
                path,
            ),
        )
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_error_messages(self, mock_run_cmd, mock_stdout):
        """Should print appropriate error messages and raise EditTempFileError"""
        errors = {
            inner.CommandNotFoundError: "failed to call run0 to start editor",
            inner.SubprocessError: "failed to edit temporary file",
        }
        mock_run_cmd.side_effect = iter(errors)
        for message in errors.values():
            with self.assertRaises(inner.EditTempFileError):
                inner.run_editor(uid=42, editor="butterfly", path="some/path")
            self.assertIn(message, mock_stdout.getvalue())
            mock_stdout.truncate(0)
            mock_stdout.seek(0)


@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_inner.run_editor")
class TestRun(TestCaseWithFiles):
    """Tests for run"""

    def edit_temp_file(self, data: bytes) -> None:
        """Helper method to simulate the user editing the temp file"""
        with open(self.temp_filename, "wb") as f:
            f.write(data)

    @mock.patch("run0edit_inner.handle_copy_to_original")
    @mock.patch("run0edit_inner.copy_file_contents")
    @mock.patch("run0edit_inner.handle_check_readonly")
    @mock.patch("run0edit_inner.check_file_exists")
    @mock.patch("os.path.realpath")
    def test_check_args(
        self, m_realpath, m_exists, m_check_ro, m_copy_file, m_copy_orig, m_run_editor, m_stdout
    ):
        """Should pass correct arguments to functions"""
        s = mock.sentinel
        m_realpath.return_value = s.realpath
        m_exists.return_value = True
        m_check_ro.return_value = s.immutable
        inner.run(s.filename, s.temp_filename, s.editor, s.uid, bgcolor=s.bgcolor)
        self.assertEqual(m_realpath.call_args.args, (s.filename,))
        self.assertEqual(m_exists.call_args.args, (s.realpath,))
        self.assertEqual(
            m_check_ro.call_args,
            ((s.realpath,), {"is_dir": False, "prompt_immutable": True}),
        )
        self.assertEqual(m_copy_file.call_args, ((s.realpath, s.temp_filename), {"create": False}))
        self.assertEqual(
            m_run_editor.call_args,
            ((), {"uid": s.uid, "editor": s.editor, "path": s.temp_filename, "bgcolor": s.bgcolor}),
        )
        self.assertEqual(
            m_copy_orig.call_args,
            (
                (s.realpath, s.temp_filename),
                {"original_file_exists": True, "immutable": s.immutable},
            ),
        )
        self.assertEqual(m_stdout.getvalue(), "")

    @mock.patch("run0edit_inner.copy_file_contents")
    def test_copy_to_temp_fail(self, mock_copy_file, mock_run_editor, mock_stdout):
        """Should print message and raise FileCopyError if copy to temp fails"""
        mock_copy_file.side_effect = inner.FileCopyError
        with self.assertRaises(inner.FileCopyError):
            inner.run(self.filename, self.temp_filename, "editor", 42)
        self.assertFalse(mock_run_editor.called)
        self.assertRegex(mock_stdout.getvalue(), " failed to copy .* to temporary file ")

    def test_edit_file(self, mock_run_editor, mock_stdout):
        """Should copy edited tempfile contents to target file"""
        text = b"Lorum ipsum dolor sit amet"
        mock_run_editor.side_effect = lambda **_: self.edit_temp_file(text)
        inner.run(self.filename, self.temp_filename, "editor", 42)
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), text)
        self.assertEqual(mock_stdout.getvalue(), "")

    @mock.patch("run0edit_inner.copy_to_original")
    def test_edit_unchanged(self, mock_copy_to_orig, mock_run_editor, mock_stdout):
        """Should not copy unmodified tempfile contents to target file"""
        inner.run(self.filename, self.temp_filename, "editor", 42)
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.file_contents)
        self.assertTrue(mock_run_editor.called)
        self.assertFalse(mock_copy_to_orig.called)
        self.assertIn("unchanged", mock_stdout.getvalue())

    @mock.patch("run0edit_inner.copy_file_contents")
    def test_new_file_no_copy(self, mock_copy_file, mock_run_editor, mock_stdout):
        """Should not try copying nonexistent file to temp file"""
        mock_run_editor.side_effect = Exception("mock run editor")
        with self.assertRaisesRegex(Exception, "mock run editor"):
            inner.run(self.new_filename, self.temp_filename, "editor", 42)
        self.assertFalse(mock_copy_file.called)
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_create_file(self, mock_run_editor, mock_stdout):
        """Should copy edited tempfile contents to new file"""
        text = b"Lorum ipsum dolor sit amet"
        mock_run_editor.side_effect = lambda **_: self.edit_temp_file(text)
        inner.run(self.new_filename, self.temp_filename, "editor", 42)
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), text)
        self.assertEqual(mock_stdout.getvalue(), "")

    @mock.patch("run0edit_inner.copy_to_original")
    def test_create_empty(self, mock_copy_to_orig, mock_run_editor, mock_stdout):
        """Should not create empty new file"""
        with open(self.temp_filename, "wb"):
            pass
        inner.run(self.new_filename, self.temp_filename, "editor", 42)
        self.assertFalse(os.path.exists(self.new_filename))
        self.assertTrue(mock_run_editor.called)
        self.assertFalse(mock_copy_to_orig.called)
        self.assertIn("not created", mock_stdout.getvalue())

    def test_immutable_declined(self, mock_run_editor, mock_stdout):
        """Should return without editing if user declines to remove immutable flag"""
        with (
            mock.patch("run0edit_inner.should_remove_immutable") as mock_ask_imm,
            mock.patch("run0edit_inner.is_immutable") as mock_is_imm,
            mock.patch("run0edit_inner.readonly_filesystem") as mock_ro_fs,
        ):
            mock_ask_imm.return_value = False
            mock_is_imm.return_value = True
            mock_ro_fs.return_value = False
            inner.run("/proc/version", self.temp_filename, "editor", 42)
        self.assertFalse(mock_run_editor.called)
        self.assertIn("declined to remove immutable attribute", mock_stdout.getvalue())


@mock.patch("sys.stdout", new_callable=io.StringIO)
class TestParseArgs(unittest.TestCase):
    """Tests for parse_args"""

    ARGS = (mock.sentinel.a0, mock.sentinel.a1, mock.sentinel.a2, mock.sentinel.a3)

    def test_three_args(self, mock_stdout):
        """Should return three provided arguments plus None"""
        self.assertEqual(inner.parse_args(self.ARGS[:3]), (*self.ARGS[:3], None))
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_four_args(self, mock_stdout):
        """Should return four provided arguments"""
        self.assertEqual(inner.parse_args(self.ARGS), self.ARGS)
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_too_few_args(self, mock_stdout):
        """Should print expected message and raise exception if too few arguments"""
        with self.assertRaises(inner.InvalidArgumentsError):
            inner.parse_args(self.ARGS[:2])
        self.assertEqual(mock_stdout.getvalue(), "run0edit_inner.py: Error: too few arguments\n")

    def test_too_many_args(self, mock_stdout):
        """Should print expected message and raise exception if too many arguments"""
        with self.assertRaises(inner.InvalidArgumentsError):
            inner.parse_args([*self.ARGS, "???"])
        self.assertEqual(mock_stdout.getvalue(), "run0edit_inner.py: Error: too many arguments\n")


@mock.patch("run0edit_inner.run")
@mock.patch("os.environ", new={"SUDO_UID": 42})
class TestMain(unittest.TestCase):
    """Tests for main"""

    ARGS = (mock.sentinel.a0, mock.sentinel.a1, mock.sentinel.a2, mock.sentinel.a3)
    EXPECTED_ARGS = ((*ARGS[:3], 42), {"bgcolor": ARGS[3], "prompt_immutable": True})

    @mock.patch("run0edit_inner.parse_args")
    def test_parses_args(self, mock_parse_args, mock_run):
        """Should parse arguments using parse_args"""
        mock_parse_args.return_value = self.ARGS
        inner.main(mock.sentinel.main_args)
        self.assertEqual(mock_parse_args.call_args, ((mock.sentinel.main_args,), {}))
        self.assertEqual(mock_run.call_args, self.EXPECTED_ARGS)

    @mock.patch("run0edit_inner.parse_args")
    def test_invalid_args(self, mock_parse_args, mock_run):
        """Should return 2 if parse_args raises InvalidArgumentsError"""
        mock_parse_args.side_effect = inner.InvalidArgumentsError
        self.assertEqual(inner.main(mock.sentinel.main_args), 2)
        self.assertFalse(mock_run.called)

    def test_normal_run(self, mock_run):
        """Should pass correct args to run and return 0"""
        self.assertEqual(inner.main(self.ARGS), 0)
        self.assertEqual(mock_run.call_args, self.EXPECTED_ARGS)

    def test_normal_run_with_uid(self, mock_run):
        """Should pass correct args to run and return 0"""
        self.assertEqual(inner.main(self.ARGS, uid=5), 0)
        self.assertEqual(
            mock_run.call_args,
            ((*self.ARGS[:3], 5), {"bgcolor": self.ARGS[3], "prompt_immutable": True}),
        )

    def test_failed_run(self, mock_run):
        """Should pass correct args to run and return 1"""
        mock_run.side_effect = inner.Run0editError
        self.assertEqual(inner.main(self.ARGS), 1)
        self.assertEqual(mock_run.call_args, self.EXPECTED_ARGS)

    @mock.patch.dict("os.environ", {"RUN0EDIT_DEBUG": "1"})
    def test_failed_run_debug(self, mock_run):
        """Should pass correct args to run and raise exception"""
        mock_run.side_effect = inner.Run0editError
        with self.assertRaises(inner.Run0editError):
            inner.main(self.ARGS)
        self.assertEqual(mock_run.call_args, self.EXPECTED_ARGS)
