#!/usr/bin/env python3

"""Unit tests for run0edit_inner.py"""

import io
import os
import shutil
import tempfile
import unittest
from unittest import mock

import run0edit_inner as inner


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
class TestAskImmutable(unittest.TestCase):
    """Tests for ask_immutable"""

    def test_dir(self, mock_stdout, mock_input):
        """Test answer on directory"""
        path = "/etc"
        inner.ask_immutable(path)
        self.assertIn(path, mock_stdout.getvalue())
        self.assertIn("directory", mock_input.call_args.args[0])

    def test_not_dir(self, mock_stdout, mock_input):
        """Test answer on non-directory"""
        path = "/etc/hosts"
        inner.ask_immutable(path)
        self.assertIn(path, mock_stdout.getvalue())
        self.assertNotIn("directory", mock_input.call_args.args[0])

    def test_answers(self, _, mock_input):
        """Test answer 'y'"""
        answers = ["y", "n", "", ".yes", "Y", "N", "YNO", "yyes", "nyan"]
        mock_input.side_effect = answers
        path = "/etc"
        for answer in answers:
            result = inner.ask_immutable(path)
            self.assertEqual(result, answer.lower().startswith("y"))


class TestHandleReadonly(unittest.TestCase):
    """Tests for handle_readonly"""

    @mock.patch("run0edit_inner.readonly_filesystem")
    def test_ro_fs(self, mock_ro_fs):
        """Path on read-only filesystem should raise correct error"""
        mock_ro_fs.return_value = True
        with self.assertRaises(inner.ReadOnlyFilesystemError):
            inner.handle_readonly("/var")

    @mock.patch("run0edit_inner.is_immutable")
    @mock.patch("run0edit_inner.ask_immutable")
    def test_immutable_with_prompt(self, mock_ask_immutable, mock_is_immutable):
        """
        Should ask user if immutable and prompt=True, and should raise correct
        error if user answers no.
        """
        mock_is_immutable.return_value = True
        mock_ask_immutable.side_effect = [True, False]
        inner.handle_readonly("/var")
        with self.assertRaises(inner.ReadOnlyImmutableError):
            inner.handle_readonly("/var")
        self.assertTrue(mock_ask_immutable.called)

    @mock.patch("run0edit_inner.is_immutable")
    @mock.patch("run0edit_inner.ask_immutable")
    def test_immutable_no_prompt(self, mock_ask_immutable, mock_is_immutable):
        """Should not ask user if immutable and prompt=False"""
        mock_is_immutable.return_value = True
        inner.handle_readonly("/var", prompt=False)
        self.assertFalse(mock_ask_immutable.called)

    def test_ro_other(self):
        """Should raise correct error in other case"""
        with self.assertRaises(inner.ReadOnlyOtherError):
            inner.handle_readonly("/var")


class TestCaseWithFiles(unittest.TestCase):
    """Base class for test cases with temp files automatically set up"""

    def setUp(self):
        """Set up test files"""
        self.filename = tempfile.mkstemp()[1]
        self.temp_filename = tempfile.mkstemp()[1]
        self.new_filename = f"{self.temp_filename}-new"
        self.new_dir = os.path.dirname(self.new_filename)
        self.file_contents = b"file contents"
        self.temp_contents = b"temp contents"
        with open(self.filename, "wb") as f:
            f.write(self.file_contents)
        with open(self.temp_filename, "wb") as f:
            f.write(self.temp_contents)

    def tearDown(self):
        """Clean up test files"""
        for path in (self.filename, self.temp_filename, self.new_filename):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


class TestCopyFileContents(TestCaseWithFiles):
    """Tests for copy_file_contents"""

    def test_copy(self):
        """Should copy file contents when src and dest both exist"""
        inner.copy_file_contents(self.filename, self.temp_filename)
        with open(self.filename, "rb") as f_src, open(self.temp_filename, "rb") as f_dest:
            self.assertEqual(f_src.read(), self.file_contents)
            self.assertEqual(f_dest.read(), self.file_contents)

    def test_missing_src(self):
        """Should raise correct error when src does not exist"""
        with self.assertRaises(inner.FileCopyError):
            inner.copy_file_contents(self.new_filename, self.temp_filename)

    def test_missing_dest(self):
        """Should raise correct error when dest does not exist"""
        with self.assertRaises(inner.FileCopyError):
            inner.copy_file_contents(self.temp_filename, self.new_filename)


@mock.patch("run0edit_inner.copy_file_contents")
class TestCopyToTemp(TestCaseWithFiles):
    """Tests for copy_to_temp"""

    RO_FILE: str = "/proc/version"
    RO_DIR: str = "/proc"

    @mock.patch("run0edit_inner.handle_readonly")
    def test_not_regular_file(self, mock_handle_ro, mock_copy):
        """Should raise error and not copy if target is not regular file"""
        with self.assertRaises(inner.NotRegularFileError):
            inner.copy_to_temp(True, "/etc", "/", self.temp_filename)
        self.assertFalse(mock_copy.called)
        self.assertFalse(mock_handle_ro.called)

    @mock.patch("run0edit_inner.readonly_filesystem")
    def test_read_only_error(self, mock_ro_fs, mock_copy):
        """Should raise error and not copy if read-only filesystem"""
        mock_ro_fs.return_value = True
        with self.assertRaises(inner.ReadOnlyFilesystemError):
            inner.copy_to_temp(True, self.RO_FILE, self.RO_DIR, self.temp_filename)
        self.assertFalse(mock_copy.called)

    @mock.patch("run0edit_inner.handle_readonly")
    def test_immutable(self, mock_handle_ro, mock_copy):
        """Should copy if read-only due to immutable flag that will be removed"""
        self.assertTrue(inner.copy_to_temp(True, self.RO_FILE, self.RO_DIR, self.temp_filename))
        self.assertEqual(mock_copy.call_args.args, (self.RO_FILE, self.temp_filename))
        self.assertEqual(mock_handle_ro.call_args.args, (self.RO_FILE,))

    @mock.patch("run0edit_inner.handle_readonly")
    def test_regular_file(self, mock_handle_ro, mock_copy):
        """Should copy if target file is writable"""
        self.assertFalse(inner.copy_to_temp(True, self.filename, "dir", self.temp_filename))
        self.assertEqual(mock_copy.call_args.args, (self.filename, self.temp_filename))
        self.assertFalse(mock_handle_ro.called)

    @mock.patch("run0edit_inner.handle_readonly")
    def test_no_directory(self, mock_handle_ro, mock_copy):
        """Should raise error if directory does not exist"""
        with self.assertRaises(inner.NoDirectoryError):
            inner.copy_to_temp(False, "...", "/no/such/directory", self.temp_filename)
        self.assertFalse(mock_copy.called)
        self.assertFalse(mock_handle_ro.called)

    @mock.patch("run0edit_inner.readonly_filesystem")
    def test_read_only_dir_error(self, mock_ro_fs, mock_copy):
        """Should raise error if directory on read-only filesystem"""
        mock_ro_fs.return_value = True
        with self.assertRaises(inner.ReadOnlyFilesystemError):
            inner.copy_to_temp(False, self.RO_FILE, self.RO_DIR, self.temp_filename)
        self.assertFalse(mock_copy.called)

    @mock.patch("run0edit_inner.handle_readonly")
    def test_immutable_dir(self, mock_handle_ro, mock_copy):
        """Should succeed if directory read-only due to immutable flag that will be removed"""
        self.assertTrue(inner.copy_to_temp(False, self.RO_FILE, self.RO_DIR, self.temp_filename))
        self.assertFalse(mock_copy.called)
        self.assertEqual(mock_handle_ro.call_args.args, (self.RO_DIR,))

    @mock.patch("run0edit_inner.handle_readonly")
    def test_regular_dir(self, mock_handle_ro, mock_copy):
        """Should copy if target file is writable"""
        self.assertFalse(
            inner.copy_to_temp(False, self.new_filename, self.new_dir, self.temp_filename)
        )
        self.assertFalse(mock_copy.called)
        self.assertFalse(mock_handle_ro.called)


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
class TestCopyToDest(TestCaseWithFiles):
    """Tests for copy_to_dest"""

    def test_file_exists_not_immutable(self, mock_chattr, mock_stdout):
        """Should copy to dest if file exists and is not immutable"""
        inner.copy_to_dest(self.filename, self.temp_filename, None)
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertFalse(mock_chattr.called)
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_new_file_not_immutable(self, mock_chattr, mock_stdout):
        """Should copy temp file contents to new file if directory is not immutable"""
        inner.copy_to_dest(self.new_filename, self.temp_filename, None)
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertFalse(mock_chattr.called)
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_file_exists_immutable(self, mock_chattr, mock_stdout):
        """Should chattr and copy to dest if file exists and is immutable"""
        inner.copy_to_dest(self.filename, self.temp_filename, "foo")
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertEqual(mock_chattr.call_args_list, [(("-i", "foo"),), (("+i", "foo"),)])
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    def test_new_file_immutable(self, mock_chattr, mock_stdout):
        """Should chattr and copy to new file if directory is immutable"""
        inner.copy_to_dest(self.new_filename, self.temp_filename, "foo")
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertEqual(mock_chattr.call_args_list, [(("-i", "foo"),), (("+i", "foo"),)])
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("run0edit_inner.copy_file_contents")
    def test_reapply_chattr_if_error(self, mock_copy, mock_chattr, mock_stdout):
        """Should chattr +i even if copy fails"""
        mock_copy.side_effect = [inner.FileCopyError]
        with self.assertRaises(inner.FileCopyError):
            inner.copy_to_dest(self.filename, self.temp_filename, "foo")
        self.assertEqual(mock_chattr.call_args_list, [(("-i", "foo"),), (("+i", "foo"),)])
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("run0edit_inner.copy_file_contents")
    def test_detect_file_contents_mismatch(self, mock_copy, mock_chattr, mock_stdout):
        """Should detect mismatch in file contents after reapplying +i"""
        mock_copy.side_effect = None
        with self.assertRaises(inner.FileContentsMismatchError):
            inner.copy_to_dest(self.filename, self.temp_filename, "foo")
        self.assertEqual(mock_chattr.call_args_list, [(("-i", "foo"),), (("+i", "foo"),)])
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("filecmp.cmp")
    def test_immutable_failed_cmp_raises_error(self, mock_cmp, mock_chattr, mock_stdout):
        """File contents mismatch should trigger error"""
        mock_cmp.side_effect = [False, FileNotFoundError]
        for _ in range(2):
            with self.assertRaises(inner.FileContentsMismatchError):
                inner.copy_to_dest(self.filename, self.temp_filename, "foo")
        self.assertEqual(mock_chattr.call_args_list, [(("-i", "foo"),), (("+i", "foo"),)] * 2)
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n" * 2)
        self.assertEqual(mock_cmp.call_args.args, (self.temp_filename, self.filename))


class TestHandleCopyToTemp(TestCaseWithFiles):
    """Tests for handle_copy_to_temp"""

    def test_copy_file_exists(self):
        """Copy should succeed when source file exists"""
        inner.handle_copy_to_temp(self.filename, "dir", self.temp_filename, True)
        with open(self.temp_filename, "rb") as f:
            self.assertEqual(f.read(), self.file_contents)

    def test_copy_no_file(self):
        """Copy should not modify temp file when source file does not exist"""
        inner.handle_copy_to_temp(self.new_filename, self.new_dir, self.temp_filename, False)
        with open(self.temp_filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)

    @mock.patch("sys.stdout", new_callable=io.StringIO)
    @mock.patch("run0edit_inner.copy_to_temp")
    def test_error_messages(self, mock_copy, mock_stdout):
        """Should print appropriate error messages and re-raise exceptions"""
        errors = {
            inner.NotRegularFileError: "not a regular file",
            inner.NoDirectoryError: "directory does not exist",
            inner.FileCopyError: "failed to copy",
            inner.ReadOnlyFilesystemError: "read-only filesystem",
            inner.ReadOnlyImmutableError: "user declined to remove immutable",
            inner.ReadOnlyOtherError: "is read-only",
        }
        mock_copy.side_effect = iter(errors)
        for exc, message in errors.items():
            with self.assertRaises(exc):
                inner.handle_copy_to_temp("foo", "bar", "baz", True)
            self.assertIn(message, mock_stdout.getvalue())
            mock_stdout.truncate(0)
            mock_stdout.seek(0)


@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_inner.run_chattr")
class TestHandleCopyToDest(TestCaseWithFiles):
    """Tests for handle_copy_to_dest"""

    def test_file_edited(self, mock_chattr, mock_stdout):
        """Should copy if temp file differs from original file"""
        inner.handle_copy_to_dest(self.filename, "dir", self.temp_filename, True, False)
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertFalse(mock_chattr.called)
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_file_edited_immutable(self, mock_chattr, mock_stdout):
        """Should copy and chattr if temp file differs from original immutable file"""
        inner.handle_copy_to_dest(self.filename, "dir", self.temp_filename, True, True)
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertEqual(
            mock_chattr.call_args_list, [(("-i", self.filename),), (("+i", self.filename),)]
        )
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("run0edit_inner.copy_to_dest")
    def test_file_unchanged(self, mock_copy_to_dest, mock_chattr, mock_stdout):
        """Should not copy if temp file has same contents as original file"""
        shutil.copyfile(self.filename, self.temp_filename)
        inner.handle_copy_to_dest(self.filename, "dir", self.temp_filename, True, True)
        self.assertFalse(mock_copy_to_dest.called)
        self.assertFalse(mock_chattr.called)
        self.assertIn("unchanged", mock_stdout.getvalue())

    def test_file_created(self, mock_chattr, mock_stdout):
        """Should copy to new file if temp file is non-empty"""
        inner.handle_copy_to_dest(self.new_filename, "dir", self.temp_filename, False, False)
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertFalse(mock_chattr.called)
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_file_created_immutable(self, mock_chattr, mock_stdout):
        """Should chattr directory and copy to new file if temp file is non-empty"""
        inner.handle_copy_to_dest(self.new_filename, "dir", self.temp_filename, False, True)
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), self.temp_contents)
        self.assertEqual(mock_chattr.call_args_list, [(("-i", "dir"),), (("+i", "dir"),)])
        self.assertEqual(mock_stdout.getvalue(), "Immutable attribute reapplied.\n")

    @mock.patch("run0edit_inner.copy_to_dest")
    def test_file_not_created_empty(self, mock_copy, mock_chattr, mock_stdout):
        """Should not create new file if temp file is empty"""
        with open(self.temp_filename, "wb"):
            pass
        inner.handle_copy_to_dest(self.new_filename, "dir", self.temp_filename, False, True)
        self.assertFalse(mock_copy.called)
        self.assertFalse(mock_chattr.called)
        self.assertIn("not created", mock_stdout.getvalue())

    @mock.patch("run0edit_inner.copy_to_dest")
    def test_error_messages(self, mock_copy, mock_chattr, mock_stdout):
        """Should print appropriate error messages and re-raise exceptions"""
        errors = {
            inner.FileCopyError: "unable to copy contents of temporary file",
            inner.ChattrError: "failed to run chattr",
            inner.FileContentsMismatchError: "does not match contents of edited tempfile",
        }
        mock_copy.side_effect = iter(errors)
        for exc, message in errors.items():
            with self.assertRaises(exc):
                inner.handle_copy_to_dest(self.filename, "dir", self.temp_filename, True, False)
            self.assertIn(message, mock_stdout.getvalue())
            mock_stdout.truncate(0)
            mock_stdout.seek(0)
        self.assertFalse(mock_chattr.called)


@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_inner.run_command")
class TestRunEditor(unittest.TestCase):
    """Tests for run_editor"""

    def test_check_args(self, mock_run_cmd, mock_stdout):
        """Should pass correct arguments to run_command"""
        editor = mock.sentinel.editor
        path = mock.sentinel.path
        inner.run_editor(uid=42, editor=editor, path=path)
        self.assertEqual(mock_run_cmd.call_args.args, ("run0", "--user=42", "--", editor, path))
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

    def edit_temp_file(self, data: bytes):
        """Helper method to simulate the user editing the temp file"""
        with open(self.temp_filename, "wb") as f:
            f.write(data)

    @mock.patch("run0edit_inner.handle_copy_to_dest")
    @mock.patch("run0edit_inner.handle_copy_to_temp")
    def test_check_args(self, mock_copy_temp, mock_copy_dest, mock_run_editor, mock_stdout):
        """Should pass correct arguments to functions"""
        editor = mock.sentinel.editor
        uid = mock.sentinel.uid
        inner.run(self.filename, self.temp_filename, editor, uid)
        directory = os.path.dirname(self.filename)
        self.assertEqual(
            mock_copy_temp.call_args.args, (self.filename, directory, self.temp_filename, True)
        )
        self.assertEqual(
            mock_run_editor.call_args.kwargs,
            {"uid": uid, "editor": editor, "path": self.temp_filename},
        )
        self.assertEqual(
            mock_copy_dest.call_args.args,
            (self.filename, directory, self.temp_filename, True, mock.ANY),
        )
        self.assertEqual(mock_stdout.getvalue(), "")

    def test_edit_file(self, mock_run_editor, mock_stdout):
        """Should copy edited tempfile contents to target file"""
        text = b"Lorum ipsum dolor sit amet"
        mock_run_editor.side_effect = lambda **_: self.edit_temp_file(text)
        inner.run(self.filename, self.temp_filename, "editor", 42)
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), text)
        self.assertEqual(mock_stdout.getvalue(), "")

    @mock.patch("run0edit_inner.copy_to_dest")
    def test_edit_unchanged(self, mock_copy_to_dest, mock_run_editor, mock_stdout):
        """Should not copy unmodified tempfile contents to target file"""
        inner.run(self.filename, self.temp_filename, "editor", 42)
        with open(self.filename, "rb") as f:
            self.assertEqual(f.read(), self.file_contents)
        self.assertTrue(mock_run_editor.called)
        self.assertFalse(mock_copy_to_dest.called)
        self.assertIn("unchanged", mock_stdout.getvalue())

    def test_create_file(self, mock_run_editor, mock_stdout):
        """Should copy edited tempfile contents to new file"""
        text = b"Lorum ipsum dolor sit amet"
        mock_run_editor.side_effect = lambda **_: self.edit_temp_file(text)
        inner.run(self.new_filename, self.temp_filename, "editor", 42)
        with open(self.new_filename, "rb") as f:
            self.assertEqual(f.read(), text)
        self.assertEqual(mock_stdout.getvalue(), "")

    @mock.patch("run0edit_inner.copy_to_dest")
    def test_create_empty(self, mock_copy_to_dest, mock_run_editor, mock_stdout):
        """Should not create empty new file"""
        with open(self.temp_filename, "wb"):
            pass
        inner.run(self.new_filename, self.temp_filename, "editor", 42)
        self.assertFalse(os.path.exists(self.new_filename))
        self.assertTrue(mock_run_editor.called)
        self.assertFalse(mock_copy_to_dest.called)
        self.assertIn("not created", mock_stdout.getvalue())

    def test_immutable_declined(self, mock_run_editor, mock_stdout):
        """Should return without editing if user declines to remove immutable flag"""
        with (
            mock.patch("run0edit_inner.ask_immutable") as mock_ask_imm,
            mock.patch("run0edit_inner.is_immutable") as mock_is_imm,
            mock.patch("run0edit_inner.readonly_filesystem") as mock_ro_fs,
        ):
            mock_ask_imm.return_value = False
            mock_is_imm.return_value = True
            mock_ro_fs.return_value = False
            inner.run("/proc/version", self.temp_filename, "editor", 42)
        self.assertFalse(mock_run_editor.called)
        self.assertIn("declined to remove immutable attribute", mock_stdout.getvalue())


@mock.patch("run0edit_inner.run")
@mock.patch("os.environ", new={"SUDO_UID": "42"})
class TestMain(unittest.TestCase):
    """Tests for main"""

    ARGS = [mock.sentinel.a0, mock.sentinel.a1, mock.sentinel.a2, mock.sentinel.a3, "--debug"]

    def test_too_few_args(self, mock_run):
        """Should return 2 if too few arguments"""
        self.assertEqual(inner.main(self.ARGS[:3]), 2)
        self.assertFalse(mock_run.called)

    def test_normal_run(self, mock_run):
        """Should pass correct args to run and return 0"""
        self.assertEqual(inner.main(self.ARGS[:4]), 0)
        self.assertEqual(mock_run.call_args.args, tuple(self.ARGS[1:4] + [42]))

    def test_normal_run_with_uid(self, mock_run):
        """Should pass correct args to run and return 0"""
        self.assertEqual(inner.main(self.ARGS[:4], uid=5), 0)
        self.assertEqual(mock_run.call_args.args, tuple(self.ARGS[1:4] + [5]))

    def test_failed_run(self, mock_run):
        """Should pass correct args to run and return 1"""
        mock_run.side_effect = inner.Run0editError
        self.assertEqual(inner.main(self.ARGS[:4]), 1)
        self.assertEqual(mock_run.call_args.args, tuple(self.ARGS[1:4] + [42]))

    def test_failed_run_debug(self, mock_run):
        """Should pass correct args to run and raise exception"""
        mock_run.side_effect = inner.Run0editError
        with self.assertRaises(inner.Run0editError):
            inner.main(self.ARGS)
        self.assertEqual(mock_run.call_args.args, tuple(self.ARGS[1:4] + [42]))
