#!/usr/bin/env python3

"""Unit tests for run0edit_main.py"""

import hashlib
import io
import os
import pathlib
import unittest
from unittest import mock

import run0edit_main as run0edit
from . import new_test_file, remove_test_file, new_test_dir, remove_test_dir


class TestVersionStringFormat(unittest.TestCase):
    """Test constant __version__"""

    def test_version_string_semver(self):
        """Version string should match semantic versioning syntax"""
        self.assertRegex(run0edit.__version__, r"[0-9]+\.[0-9]+\.[0-9]+")


class TestInnerScriptPath(unittest.TestCase):
    """Test constant INNER_SCRIPT_PATH"""

    def test_inner_script_path(self):
        """Should have expected value"""
        self.assertEqual(run0edit.INNER_SCRIPT_PATH, "/usr/libexec/run0edit/run0edit_inner.py")


class TestInnerScriptSha256(unittest.TestCase):
    """Test constant INNER_SCRIPT_SHA256"""

    def test_inner_script_sha256(self):
        """Inner script should have expected SHA-256 hash"""
        with open("run0edit_inner.py", "rb") as f:
            file_hash = hashlib.sha256(f.read())
        self.assertEqual(file_hash.hexdigest(), run0edit.INNER_SCRIPT_SHA256)


class TestValidateInnerScript(unittest.TestCase):
    """Tests for validate_inner_script"""

    @mock.patch("run0edit_main.open", create=True)
    def test_check_args(self, mock_open):
        """Should read from expected path"""
        with self.assertRaisesRegex(TypeError, "object supporting the buffer API required"):
            run0edit.validate_inner_script()
        self.assertEqual(mock_open.call_args.args, (run0edit.INNER_SCRIPT_PATH, "rb"))

    @mock.patch("run0edit_main.INNER_SCRIPT_PATH", "run0edit_inner.py")
    def test_valid_inner_script(self):
        """Should return True when computing hash of inner script file"""
        self.assertTrue(run0edit.validate_inner_script())

    @mock.patch("run0edit_main.INNER_SCRIPT_PATH", "run0edit_main.py")
    def test_invalid_inner_script(self):
        """Should return False if pointed to a file with wrong contents"""
        self.assertFalse(run0edit.validate_inner_script())

    @mock.patch("run0edit_main.INNER_SCRIPT_PATH", "/no/such/file/exists")
    def test_missing_inner_script(self):
        """Should return False if pointed to a file that doesn't exist"""
        self.assertFalse(run0edit.validate_inner_script())


class TestIsValidExecutable(unittest.TestCase):
    """Tests for is_valid_executable"""

    def test_not_abs(self):
        """Should return false if path is not absolute"""
        self.assertFalse(run0edit.is_valid_executable("vim"))

    def test_not_exists(self):
        """Should return false if path does not exist"""
        self.assertFalse(run0edit.is_valid_executable("/usr/bin/no-such-file-asdf"))

    def test_not_file(self):
        """Should return false if path is not a file"""
        self.assertFalse(run0edit.is_valid_executable("/usr/bin"))

    def test_required_permissions(self):
        """Should return true only if file is readable and executable by user"""
        file = new_test_file()
        for mode in (0o000, 0o100, 0o200, 0o400, 0o600):
            os.chmod(file, mode)
            self.assertFalse(run0edit.is_valid_executable(file))
        for mode in (0o500, 0o700):
            os.chmod(file, mode)
            self.assertTrue(run0edit.is_valid_executable(file))
        remove_test_file(file)


class TestEditorPath(unittest.TestCase):
    """Tests for editor_path"""

    @mock.patch("run0edit_main.open", create=True)
    def test_default_conf_path(self, mock_open):
        """Should check expected default configuration path"""
        mock_open.side_effect = Exception("mock open")
        with self.assertRaisesRegex(Exception, "mock open"):
            run0edit.editor_path()
        self.assertEqual(mock_open.call_args.args, ("/etc/run0edit/editor.conf", "r"))

    @mock.patch("run0edit_main.open", create=True)
    def test_provided_conf_path(self, mock_open):
        """Should check provided configuration path"""
        mock_open.side_effect = Exception("mock open")
        with self.assertRaisesRegex(Exception, "mock open"):
            run0edit.editor_path(conf_paths=("/some/other/path.conf",))
        self.assertEqual(mock_open.call_args.args, ("/some/other/path.conf", "r"))

    @mock.patch("run0edit_main.find_command")
    def test_read_conf_paths(self, mock_find_cmd):
        """Should read and validate editor path from conf files"""
        conf1 = new_test_file()
        conf2 = new_test_file(b"/bin/true\n")
        with open(conf1, "w", encoding="utf8") as f:
            f.write(conf1)
        editor = run0edit.editor_path(conf_paths=(f"{conf1}-bad", conf1, conf2))
        self.assertEqual(editor, "/bin/true")
        self.assertFalse(mock_find_cmd.called)
        remove_test_file(conf1)
        remove_test_file(conf2)

    @mock.patch("run0edit_main.find_command")
    def test_default_fallbacks(self, mock_find_cmd):
        """Should try to find expected default fallback editors, and return None if none found"""
        mock_find_cmd.return_value = None
        self.assertIsNone(run0edit.editor_path(conf_paths=()))
        expected = ("nano", "vi")
        self.assertEqual(mock_find_cmd.call_args_list, [((cmd,), {}) for cmd in expected])

    def test_provided_fallbacks(self):
        """Should try to find expected default fallback editors, and return None if none found"""
        fallbacks = ("nonexistent-cmd-asdf", "", "true")
        editor = run0edit.editor_path(conf_paths=(), fallbacks=fallbacks)
        self.assertIn(editor, ("/bin/true", "/usr/bin/true"))


class TestDirectoryDoesNotExist(unittest.TestCase):
    """Tests for directory_does_not_exist"""

    def setUp(self):
        """Set up test directory"""
        self.test_dir = new_test_dir()

    def tearDown(self):
        """Remove test directory"""
        remove_test_dir(self.test_dir)

    def test_fs_root(self):
        """Should return false for filesystem root /"""
        self.assertIs(run0edit.directory_does_not_exist("/"), False)

    def test_exists(self):
        """Should return false when directory exists, whether or not path itself exists"""
        file = f"{self.test_dir}/foo.txt"
        self.assertIs(run0edit.directory_does_not_exist(file), False)
        pathlib.Path(file).touch()
        self.assertIs(run0edit.directory_does_not_exist(file), False)

    def test_unreadable_final_dir(self):
        """Should return false when directory exists, even if contents are inaccessible"""
        file = f"{self.test_dir}/foo.txt"
        os.chmod(self.test_dir, 0o000)
        self.assertIs(run0edit.directory_does_not_exist(file), False)
        os.chmod(self.test_dir, 0o700)

    def test_unreadable_middle_dir(self):
        """Should return None if unable to check directory existence"""
        file = f"{self.test_dir}/foo/bar.txt"
        os.chmod(self.test_dir, 0o000)
        self.assertIsNone(run0edit.directory_does_not_exist(file))
        os.chmod(self.test_dir, 0o400)
        self.assertTrue(run0edit.directory_does_not_exist(file))
        os.chmod(self.test_dir, 0o700)

    def test_unreadable_subdir(self):
        """
        Should return None if missing executable bit on directory prevents
        checking directory existence.
        """
        os.mkdir(f"{self.test_dir}/foo")
        file = f"{self.test_dir}/foo/bar/spam.txt"
        os.chmod(self.test_dir, 0o600)
        self.assertIsNone(run0edit.directory_does_not_exist(file))
        os.chmod(self.test_dir, 0o700)

    def test_not_directory_intermediate(self):
        """Should return True if file encountered where directory should be"""
        pathlib.Path(f"{self.test_dir}/foo").touch()
        file = f"{self.test_dir}/foo/bar/spam.txt"
        self.assertTrue(run0edit.directory_does_not_exist(file))

    def test_not_directory_final(self):
        """Should return True if parent is file instead of directory"""
        pathlib.Path(f"{self.test_dir}/foo").touch()
        file = f"{self.test_dir}/foo/bar.txt"
        self.assertTrue(run0edit.directory_does_not_exist(file))

    def test_unknown_parent_type(self):
        """Should return None if parent exists but unable to determine if it's a directory"""
        os.mkdir(f"{self.test_dir}/foo")
        file = f"{self.test_dir}/foo/bar.txt"
        os.chmod(self.test_dir, 0o600)
        self.assertIsNone(run0edit.directory_does_not_exist(file))
        os.chmod(self.test_dir, 0o700)


class TestMakeTempFile(unittest.TestCase):
    """Tests for make_temp_file"""

    def test_make_temp_file(self):
        """Should create temp file with name derived from given path"""
        filename = "spam.txt"
        path = f"/foo/bar/{filename}"
        temp = run0edit.make_temp_file(path)
        temp_filename = os.path.basename(temp)
        self.assertTrue(temp_filename.startswith(filename))
        self.assertGreaterEqual(len(temp_filename.removeprefix(filename)), 8)
        self.assertTrue(os.path.isfile(temp))
        self.assertEqual(os.path.getsize(temp), 0)
        os.remove(temp)

    def test_long_filename(self):
        """Should truncate long filenames"""
        filename = "long" * 100
        temp = run0edit.make_temp_file(filename)
        self.assertLess(len(os.path.basename(temp)), 100)
        os.remove(temp)


class TestCleanTempFile(unittest.TestCase):
    """Tests for clean_temp_file"""

    def setUp(self):
        """Set up test file"""
        self.empty_file = new_test_file()
        self.non_empty_file = new_test_file(b"asdf")

    def tearDown(self):
        """Clean up test file"""
        remove_test_file(self.empty_file)
        remove_test_file(self.non_empty_file)

    def test_clean_unconditional(self):
        """Should remove file unconditionally by default"""
        run0edit.clean_temp_file(self.empty_file)
        self.assertFalse(os.path.exists(self.empty_file))
        run0edit.clean_temp_file(self.non_empty_file)
        self.assertFalse(os.path.exists(self.non_empty_file))

    def test_clean_only_if_empty(self):
        """Should only remove empty files with option passed"""
        run0edit.clean_temp_file(self.empty_file, only_if_empty=True)
        self.assertFalse(os.path.exists(self.empty_file))
        run0edit.clean_temp_file(self.non_empty_file, only_if_empty=True)
        self.assertTrue(os.path.exists(self.non_empty_file))


class TestEscapePath(unittest.TestCase):
    """Tests for escape_path"""

    def test_escape_path(self):
        """Should escape backslashes and double-quotes"""
        test_cases_changed = {
            "\\": "\\\\",
            '"': '\\"',
            r'\\\/""\"': r"\\\\\\/\"\"\\\"",
        }
        test_cases_unchanged = ["~`!@#$%^&*/()-_'“”=+[]{}|;:,.<>/?", "蟒蛇", "Ŝ≜"]
        for path, output in test_cases_changed.items():
            self.assertEqual(run0edit.escape_path(path), output)
        for case in test_cases_unchanged:
            self.assertEqual(run0edit.escape_path(case), case)


class TestSystemdSandboxProperties(unittest.TestCase):
    """Tests for SYSTEMD_SANDBOX_PROPERTIES constant"""

    def test_property_list(self):
        """Should have right number and format of items"""
        items = run0edit.SYSTEMD_SANDBOX_PROPERTIES
        self.assertEqual(len(items), 25)
        for prop in items:
            self.assertIsInstance(prop, str)
            self.assertIn("=", prop)
            key, value = prop.split("=", maxsplit=1)
            self.assertRegex(key, "[A-Z][A-Za-z]*")
            self.assertTrue(value.isascii())


class TestSandboxPath(unittest.TestCase):
    """Tests for sandbox_path"""

    def setUp(self):
        """Set up temporary directory"""
        self.tempdir = new_test_dir()

    def tearDown(self):
        """Remove temporary directory"""
        remove_test_dir(self.tempdir)

    def test_path_exists(self):
        """Should not modify path to existing file without symlinks"""
        path = f"{self.tempdir}/foo.txt"
        pathlib.Path(path).touch()
        self.assertEqual(run0edit.sandbox_path(path), path)

    def test_path_does_not_exist(self):
        """Should give directory containing path that doesn't exist"""
        path = f"{self.tempdir}/foo.txt"
        self.assertEqual(run0edit.sandbox_path(path), self.tempdir)

    def test_symlink_file(self):
        """Should follow symlink and give real path"""
        file_path = f"{self.tempdir}/foo"
        symlink_path = f"{self.tempdir}/bar"
        pathlib.Path(file_path).touch()
        os.symlink(file_path, symlink_path)
        self.assertEqual(run0edit.sandbox_path(symlink_path), file_path)

    def test_symlink_dir(self):
        """Should resolve directory symlinks"""
        dir_path = f"{self.tempdir}/foo"
        symlink = f"{self.tempdir}/bar"
        os.mkdir(dir_path)
        os.symlink(dir_path, symlink)
        file_path = f"{dir_path}/file.txt"
        symlinked_file_path = f"{symlink}/file.txt"
        self.assertEqual(run0edit.sandbox_path(symlinked_file_path), dir_path)
        pathlib.Path(file_path).touch()
        self.assertEqual(run0edit.sandbox_path(symlinked_file_path), file_path)


@mock.patch("run0edit_main.find_command")
class TestBuildRun0Arguments(unittest.TestCase):
    """Tests for build_run0_arguments"""

    def test_run0_not_found(self, mock_find_cmd):
        """Should raise exception if run0 not found"""
        mock_find_cmd.side_effect = lambda cmd: None if cmd == "run0" else cmd
        with self.assertRaisesRegex(run0edit.MissingCommandError, "run0"):
            run0edit.build_run0_arguments(mock.ANY, mock.ANY, mock.ANY)

    def test_python3_not_found(self, mock_find_cmd):
        """Should raise exception if python3 not found"""
        mock_find_cmd.side_effect = lambda cmd: None if cmd == "python3" else cmd
        with self.assertRaisesRegex(run0edit.MissingCommandError, "python3"):
            run0edit.build_run0_arguments(mock.ANY, mock.ANY, mock.ANY)

    def test_args(self, mock_find_cmd):
        """Should return expected arguments"""
        mock_find_cmd.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        path = new_test_file()
        temp_path = "/path/to/temp/file"
        editor = "/usr/bin/vim"
        args = run0edit.build_run0_arguments(path, temp_path, editor)
        props = run0edit.SYSTEMD_SANDBOX_PROPERTIES
        self.assertEqual(len(args), len(props) + 8)
        self.assertEqual(args[0], "/usr/bin/run0")
        self.assertTrue(args[1].startswith("--description="))
        for arg, prop in zip(args[2:], props):
            self.assertEqual(arg, "--property=" + prop)
        self.assertEqual(args[-6], f'--property=ReadWritePaths="{path}" "{temp_path}"')
        self.assertEqual(args[-5], "/usr/bin/python3")
        self.assertEqual(args[-4], run0edit.INNER_SCRIPT_PATH)
        self.assertEqual(args[-3], path)
        self.assertEqual(args[-2], temp_path)
        self.assertEqual(args[-1], editor)
        remove_test_file(path)

    def test_read_write_paths(self, mock_find_cmd):
        """Should escape correct paths in ReadWritePaths"""
        mock_find_cmd.side_effect = lambda cmd: cmd
        path = '/blahblah/"foo\\bar/spam.txt'
        temp_path = '"temp"/file'
        args = run0edit.build_run0_arguments(path, temp_path, "...")
        rw_paths = r'--property=ReadWritePaths="/blahblah/\"foo\\bar" "\"temp\"/file"'
        self.assertEqual(args[-6], rw_paths)

    def test_debug_arg(self, mock_find_cmd):
        """Should append --debug with debug option"""
        mock_find_cmd.side_effect = lambda cmd: cmd
        args = run0edit.build_run0_arguments("foo", "bar", "baz")
        args_debug = run0edit.build_run0_arguments("foo", "bar", "baz", debug=True)
        self.assertEqual(args + ["--debug"], args_debug)


class TestPrintErr(unittest.TestCase):
    """Tests for print_err"""

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_print_err(self, mock_stderr):
        """Should output text to stderr with word wrapping"""
        text = "Lorem ipsum dolor sit amet " * 10
        run0edit.print_err(text)
        output = mock_stderr.getvalue()
        self.assertTrue(output.startswith("run0edit: "))
        self.assertTrue(max(len(line) for line in output.split("\n")) <= 80)
        unwrapped = output.replace("\n", " ")
        self.assertEqual(unwrapped.removeprefix("run0edit: ").strip(), text.strip())


class TestValidatePath(unittest.TestCase):
    """Tests for validate_path"""

    def setUp(self):
        """Set up test file"""
        self.path = new_test_file(mode=0o000)

    def tearDown(self):
        """Remove test file"""
        remove_test_file(self.path)

    def test_directory(self):
        """Should fail if path is directory."""
        self.assertEqual(run0edit.validate_path("/var"), "/var is a directory.")

    def test_user_writable(self):
        """Should fail if path is writable by current user"""
        os.chmod(self.path, 0o600)
        self.assertEqual(
            run0edit.validate_path(self.path),
            f"{self.path} is writable by the current user; run0edit is unnecessary.",
        )

    @mock.patch("run0edit_main.readonly_filesystem")
    def test_readonly(self, mock_ro_fs):
        """Should fail if path is on read-only filesystem"""
        mock_ro_fs.return_value = True
        self.assertEqual(
            run0edit.validate_path(self.path), f"{self.path} is on a read-only filesystem."
        )
        self.assertEqual(mock_ro_fs.call_args.args, (self.path,))

    @mock.patch("run0edit_main.readonly_filesystem")
    def test_readonly_directory(self, mock_ro_fs):
        """Should fail if directory is on read-only filesystem"""
        mock_ro_fs.side_effect = [None, True]
        self.assertEqual(
            run0edit.validate_path(self.path), f"{self.path} is on a read-only filesystem."
        )
        self.assertEqual(mock_ro_fs.call_args.args, (os.path.dirname(self.path),))

    def test_path_does_not_exist(self):
        """Should fail if directory does not exist"""
        self.assertEqual(
            run0edit.validate_path(f"{self.path}-dir/foo.txt"), f"No such directory {self.path}-dir"
        )

    def test_success(self):
        """Should succeed (returning None) if path is valid"""
        self.assertIsNone(run0edit.validate_path(self.path))


@mock.patch("subprocess.run")
@mock.patch("run0edit_main.find_command", lambda cmd: f"/usr/bin/{cmd}")
class TestRun(unittest.TestCase):
    """Tests for run"""

    def setUp(self):
        """Set up test file"""
        self.path = new_test_file(mode=0o000)

    def tearDown(self):
        """Remove test file"""
        remove_test_file(self.path)

    @mock.patch("run0edit_main.validate_path")
    def test_validates_path_succeeded(self, mock_validate, mock_subproc):
        """Should validate path and continue if valid"""
        mock_validate.return_value = None
        run0edit.run(self.path, "...")
        self.assertEqual(mock_validate.call_args.args, (self.path,))
        self.assertTrue(mock_subproc.called)

    @mock.patch("run0edit_main.print_err")
    @mock.patch("run0edit_main.validate_path")
    def test_path_validation_failed(self, mock_validate, mock_print_err, mock_subproc):
        """Should validate path and exit with an error message if not valid"""
        mock_validate.return_value = "some error message"
        self.assertEqual(run0edit.run(self.path, "..."), 1)
        self.assertEqual(mock_validate.call_args.args, (self.path,))
        self.assertEqual(mock_print_err.call_args.args, ("some error message",))
        self.assertFalse(mock_subproc.called)

    def test_creates_temp_file(self, mock_subproc):
        """Should create empty temp file that's passed to subprocess.run"""
        mock_subproc.side_effect = Exception("mock subproc")
        editor = "/bin/ed"
        with self.assertRaisesRegex(Exception, "mock subproc"):
            run0edit.run(self.path, editor)
        (args,) = mock_subproc.call_args.args
        temp_filename = args[-2]
        self.assertNotEqual(self.path, temp_filename)
        self.assertTrue(os.path.isfile(temp_filename))
        self.assertEqual(os.path.getsize(temp_filename), 0)
        os.remove(temp_filename)

    @mock.patch("os.geteuid")
    def test_check_args(self, mock_geteuid, mock_subproc):
        """Should pass expected arguments to subprocess.run"""
        mock_geteuid.return_value = 1
        editor = "/usr/sbin/butterfly"
        run0edit.run(self.path, editor)
        (args,) = mock_subproc.call_args.args
        temp_filename = args[-2]
        expected_args = run0edit.build_run0_arguments(self.path, temp_filename, editor)
        self.assertEqual(args, expected_args)
        kwargs = mock_subproc.call_args.kwargs
        self.assertEqual(kwargs, {"env": mock.ANY, "check": False})
        false_bool_strings = ("0", "no", "n", "false", "f", "off")
        self.assertNotIn(kwargs["env"].get("SYSTEMD_ADJUST_TERMINAL_TITLE"), false_bool_strings)

    @mock.patch("os.geteuid")
    def test_adjust_terminal_title(self, mock_geteuid, mock_subproc):
        """Should not adjust terminal title if run as root"""
        mock_geteuid.return_value = 0
        editor = "/usr/sbin/butterfly"
        run0edit.run(self.path, editor)
        env = mock_subproc.call_args.kwargs["env"]
        self.assertEqual(env.get("SYSTEMD_ADJUST_TERMINAL_TITLE"), "false")

    @staticmethod
    def mock_editor_process(args, **_) -> int:
        """Mock subprocess.run that writes text to temp file"""
        text = os.environ.get("MOCK_TEXT")
        if text is not None:
            with open(args[-2], "w", encoding="utf8") as f:
                f.write(os.environ["MOCK_TEXT"])
        ret = mock.Mock()
        ret.returncode = int(os.environ["MOCK_RETCODE"])
        return ret

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_run_success(self, mock_stderr, mock_subproc):
        """Should clean up temp file and return 0 if subprocess succeeds"""
        mock_subproc.side_effect = self.mock_editor_process
        with mock.patch.dict("os.environ", {"MOCK_TEXT": "foo", "MOCK_RETCODE": "0"}):
            self.assertEqual(run0edit.run(self.path, "..."), 0)
        (args,) = mock_subproc.call_args.args
        temp_filename = args[-2]
        self.assertFalse(os.path.exists(temp_filename))
        self.assertEqual(mock_stderr.getvalue(), "")

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_run_fail_nonempty(self, mock_stderr, mock_subproc):
        """Should return nonzero and not clean non-empty tempfile if subprocess fails"""
        mock_subproc.side_effect = self.mock_editor_process
        with mock.patch.dict("os.environ", {"MOCK_TEXT": "foo", "MOCK_RETCODE": "42"}):
            self.assertEqual(run0edit.run(self.path, "..."), 42)
        (args,) = mock_subproc.call_args.args
        temp_filename = args[-2]
        self.assertTrue(os.path.exists(temp_filename))
        os.remove(temp_filename)
        self.assertEqual(mock_stderr.getvalue(), "")

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_run_fail_empty(self, mock_stderr, mock_subproc):
        """Should return nonzero and clean empty tempfile if subprocess fails"""
        mock_subproc.side_effect = self.mock_editor_process
        with mock.patch.dict("os.environ", {"MOCK_RETCODE": "5"}):
            self.assertEqual(run0edit.run(self.path, "..."), 5)
        (args,) = mock_subproc.call_args.args
        temp_filename = args[-2]
        self.assertFalse(os.path.exists(temp_filename))
        self.assertEqual(mock_stderr.getvalue(), "")

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_run_namespace_creation_fail(self, mock_stderr, mock_subproc):
        """Should return 1 and clean tempfile if subprocess fails with exit status 226"""
        mock_subproc.side_effect = self.mock_editor_process
        with mock.patch.dict("os.environ", {"MOCK_TEXT": "foo", "MOCK_RETCODE": "226"}):
            self.assertEqual(run0edit.run(self.path, "..."), 1)
        (args,) = mock_subproc.call_args.args
        temp_filename = args[-2]
        self.assertFalse(os.path.exists(temp_filename))
        self.assertIn("No such directory", mock_stderr.getvalue())


@mock.patch("sys.stderr", new_callable=io.StringIO)
@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_main.run")
class TestMain(unittest.TestCase):
    """Tests for main"""

    USAGE_TEXT: str = "usage: run0edit [-h] [-v] [--editor EDITOR] FILE [FILE ...]"
    DESCRIPTION: str = "run0edit allows a permitted user to edit a file as root."

    @mock.patch("sys.argv", [])
    def test_no_args(self, mock_run, mock_stdout, mock_stderr):
        """Should show usage and exit with code 2 if no arguments passed"""
        with self.assertRaisesRegex(SystemExit, "2"):
            run0edit.main()
        self.assertFalse(mock_run.called)
        self.assertEqual(mock_stdout.getvalue(), "")
        msg = mock_stderr.getvalue().strip()
        error_text = "run0edit: error: the following arguments are required: FILE"
        self.assertEqual(msg, f"{self.USAGE_TEXT}\n{error_text}")

    def test_help(self, mock_run, mock_stdout, mock_stderr):
        """Should show usage and exit normally if called with -h or --help"""
        with (
            mock.patch("sys.argv", ["run0edit", "--help"]),
            self.assertRaisesRegex(SystemExit, "0"),
        ):
            run0edit.main()
        help_text = mock_stdout.getvalue()
        self.assertTrue(help_text.startswith(f"{self.USAGE_TEXT}\n\n{self.DESCRIPTION}"))
        mock_stdout.truncate(0)
        mock_stdout.seek(0)
        with (
            mock.patch("sys.argv", ["run0edit", "-h"]),
            self.assertRaisesRegex(SystemExit, "0"),
        ):
            run0edit.main()
        self.assertEqual(mock_stdout.getvalue(), help_text)
        self.assertEqual(mock_stderr.getvalue(), "")
        self.assertFalse(mock_run.called)

    def test_version(self, mock_run, mock_stdout, mock_stderr):
        """Should show version and exit normally if called with -v or --version"""
        with (
            mock.patch("sys.argv", ["run0edit", "--version"]),
            self.assertRaisesRegex(SystemExit, "0"),
        ):
            run0edit.main()
        expected_version_text = f"run0edit {run0edit.__version__}\n"
        self.assertEqual(mock_stdout.getvalue(), expected_version_text)
        mock_stdout.truncate(0)
        mock_stdout.seek(0)
        with (
            mock.patch("sys.argv", ["run0edit", "-v"]),
            self.assertRaisesRegex(SystemExit, "0"),
        ):
            run0edit.main()
        self.assertEqual(mock_stdout.getvalue(), expected_version_text)
        self.assertEqual(mock_stderr.getvalue(), "")
        self.assertFalse(mock_run.called)

    @mock.patch("sys.argv", ["run0edit", "--editor=/bin/true", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script")
    def test_valid_inner_script(self, mock_validate, mock_run, mock_stdout, mock_stderr):
        """Should continue to rest of function if validate_inner_script succeeds"""
        mock_validate.return_value = True
        run0edit.main()
        self.assertTrue(mock_validate.called)
        self.assertTrue(mock_run.called)
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertEqual(mock_stderr.getvalue(), "")

    @mock.patch("sys.argv", ["run0edit", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script")
    def test_invalid_inner_script(self, mock_validate, mock_run, mock_stdout, mock_stderr):
        """Should fail with expected error if validate_inner_script fails"""
        mock_validate.return_value = False
        self.assertEqual(run0edit.main(), 1)
        self.assertTrue(mock_validate.called)
        self.assertFalse(mock_run.called)
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertRegex(
            mock_stderr.getvalue().replace("\n", " "),
            "^run0edit: Inner script was not found .* or did not have expected SHA-256 hash",
        )

    @mock.patch("sys.argv", ["run0edit", "--editor=/usr/bin/butterfly", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.editor_path")
    @mock.patch("run0edit_main.is_valid_executable")
    def test_valid_editor(
        self, mock_valid_exe, mock_editor_path, mock_run, mock_stdout, mock_stderr
    ):
        """Should use valid editor passed as command-line argument"""
        # pylint: disable=too-many-arguments,too-many-positional-arguments
        mock_valid_exe.return_value = True
        run0edit.main()
        self.assertEqual(mock_valid_exe.call_args.args, ("/usr/bin/butterfly",))
        self.assertFalse(mock_editor_path.called)
        self.assertEqual(mock_run.call_args.args, ("asdf", "/usr/bin/butterfly"))
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertEqual(mock_stderr.getvalue(), "")

    @mock.patch("sys.argv", ["run0edit", "--editor=/etc/hosts", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.editor_path")
    @mock.patch("run0edit_main.is_valid_executable")
    def test_invalid_editor(
        self, mock_valid_exe, mock_editor_path, mock_run, mock_stdout, mock_stderr
    ):
        """Should fail if invalid editor passed as command-line argument"""
        # pylint: disable=too-many-arguments,too-many-positional-arguments
        mock_valid_exe.return_value = False
        self.assertEqual(run0edit.main(), 1)
        self.assertEqual(mock_valid_exe.call_args.args, ("/etc/hosts",))
        self.assertFalse(mock_editor_path.called)
        self.assertFalse(mock_run.called)
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertEqual(
            mock_stderr.getvalue(),
            "run0edit: --editor must be an absolute path to an executable file\n",
        )

    @mock.patch("sys.argv", ["run0edit", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.editor_path")
    def test_editor_not_found(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should fail with expected message if unable to find editor"""
        mock_editor_path.return_value = None
        self.assertEqual(run0edit.main(), 1)
        self.assertFalse(mock_run.called)
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertRegex(mock_stderr.getvalue(), r"^run0edit: Editor not found\.")

    @mock.patch("sys.argv", ["run0edit", "path1", "path2"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.editor_path")
    def test_successful_run(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should pass expected arguments to run and exit successfully"""
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.return_value = 0
        self.assertEqual(run0edit.main(), 0)
        paths = ("path1", "path2")
        self.assertEqual(
            mock_run.call_args_list, [((path, editor), {"debug": False}) for path in paths]
        )
        self.assertEqual(mock_editor_path.call_count, 1)
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertEqual(mock_stderr.getvalue(), "")

    @mock.patch("sys.argv", ["run0edit", "path1", "path2", "path3"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.editor_path")
    def test_failed_run(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should return as soon as a run returns nonzero"""
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.side_effect = [0, 42, 0]
        self.assertEqual(run0edit.main(), 42)
        self.assertEqual(mock_run.call_args.args, ("path2", editor))
        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertEqual(mock_stderr.getvalue(), "")

    @mock.patch("sys.argv", ["run0edit", "example/path"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.editor_path")
    def test_missing_command(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should return 1 if command missing"""
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.side_effect = run0edit.MissingCommandError("foo")
        self.assertEqual(run0edit.main(), 1)
        self.assertEqual(mock_run.call_args.args, ("example/path", editor))
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertEqual(mock_stderr.getvalue(), "run0edit: command `foo` not found\n")

    @mock.patch("sys.argv", ["run0edit", "--debug", "example/path"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.editor_path")
    def test_missing_command_debug(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """
        In debug mode, should pass debug argument to `run`, and raise expected
        error if command missing.
        """
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.side_effect = run0edit.MissingCommandError("foo")
        with self.assertRaisesRegex(run0edit.MissingCommandError, "foo"):
            run0edit.main()
        self.assertEqual(mock_run.call_args.kwargs, {"debug": True})
        self.assertEqual(mock_stdout.getvalue(), "")
        self.assertEqual(mock_stderr.getvalue(), "run0edit: command `foo` not found\n")
