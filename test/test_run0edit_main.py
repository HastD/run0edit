#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Unit tests for run0edit_main.py"""

import hashlib
import io
import os
import pathlib
import re
import shutil
import unittest
from collections.abc import Callable, Sequence
from typing import Any
from unittest import mock

import pytest

import run0edit_main as run0edit

from . import new_test_dir, new_test_file, remove_test_dir, remove_test_file


class TestGlobalConstants(unittest.TestCase):
    """Tests for global constants"""

    def test_version_string_semver(self):
        """__version__ should match semantic versioning syntax"""
        assert re.search(r"[0-9]+\.[0-9]+\.[0-9]+", run0edit.__version__)

    def test_inner_script_path(self):
        """INNER_SCRIPT_PATH should have expected value"""
        assert run0edit.INNER_SCRIPT_PATH == "/usr/libexec/run0edit/run0edit_inner.py"

    def test_inner_script_b2(self):
        """INNER_SCRIPT_B2 should equal BLAKE2b hash of inner script"""
        with open("run0edit_inner.py", "rb") as f:
            file_hash = hashlib.blake2b(f.read(), digest_size=32)
        assert file_hash.hexdigest() == run0edit.INNER_SCRIPT_B2

    def test_default_conf_path(self):
        """DEFAULT_CONF_PATH should have expected value"""
        assert run0edit.DEFAULT_CONF_PATH == "/etc/run0edit/editor.conf"

    def test_system_call_deny(self):
        """SYSTEM_CALL_DENY should have expected number and format of items"""
        assert len(run0edit.SYSTEM_CALL_DENY) == 10
        for item in run0edit.SYSTEM_CALL_DENY:
            assert re.search(r"^@?[a-zA-Z0-9_-]+$", item)

    def test_systemd_sandbox_properties(self):
        """SYSTEMD_SANDBOX_PROPERTIES should have expected number and format of items"""
        assert len(run0edit.SYSTEMD_SANDBOX_PROPERTIES) == 24
        for prop in run0edit.SYSTEMD_SANDBOX_PROPERTIES:
            assert isinstance(prop, str)
            assert "=" in prop
            key, value = prop.split("=", maxsplit=1)
            assert re.search("[A-Z][A-Za-z]*", key)
            assert value.isascii()


class TestValidateInnerScript(unittest.TestCase):
    """Tests for validate_inner_script"""

    @mock.patch("run0edit_main.open", create=True)
    def test_check_args(self, mock_open):
        """Should read from expected path"""
        with pytest.raises(TypeError, match="object supporting the buffer API required"):
            run0edit.validate_inner_script()
        mock_open.assert_called_once_with(run0edit.INNER_SCRIPT_PATH, "rb")

    @mock.patch("run0edit_main.INNER_SCRIPT_PATH", "run0edit_inner.py")
    def test_valid_inner_script(self):
        """Should return True when computing hash of inner script file"""
        assert run0edit.validate_inner_script()

    @mock.patch("run0edit_main.INNER_SCRIPT_PATH", "run0edit_main.py")
    def test_invalid_inner_script(self):
        """Should return False if pointed to a file with wrong contents"""
        assert not run0edit.validate_inner_script()

    @mock.patch("run0edit_main.INNER_SCRIPT_PATH", "/no/such/file/exists")
    def test_missing_inner_script(self):
        """Should return False if pointed to a file that doesn't exist"""
        assert not run0edit.validate_inner_script()


class TestIsValidExecutable(unittest.TestCase):
    """Tests for is_valid_executable"""

    def test_not_abs(self):
        """Should return false if path is not absolute"""
        assert not run0edit.is_valid_executable("vim")

    def test_not_exists(self):
        """Should return false if path does not exist"""
        assert not run0edit.is_valid_executable("/usr/bin/no-such-file-asdf")

    def test_not_file(self):
        """Should return false if path is not a file"""
        assert not run0edit.is_valid_executable("/usr/bin")

    def test_required_permissions(self):
        """Should return true only if file is readable and executable by user"""
        file = new_test_file()
        for mode in (0o000, 0o100, 0o200, 0o400, 0o600):
            os.chmod(file, mode)
            assert not run0edit.is_valid_executable(file)
        for mode in (0o500, 0o700):
            os.chmod(file, mode)
            assert run0edit.is_valid_executable(file)
        remove_test_file(file)


class TestGetEditorPathFromConf(unittest.TestCase):
    """Tests for get_editor_path_from_conf"""

    @mock.patch("run0edit_main.open", create=True)
    def test_default_conf_path(self, mock_open):
        """Should check expected default configuration path"""
        mock_open.side_effect = Exception("mock open")
        with pytest.raises(Exception, match="mock open"):
            run0edit.get_editor_path_from_conf()
        mock_open.assert_called_once_with(run0edit.DEFAULT_CONF_PATH, encoding=mock.ANY)

    @mock.patch("run0edit_main.open", create=True)
    def test_provided_conf_path(self, mock_open):
        """Should check provided configuration path"""
        mock_open.side_effect = Exception("mock open")
        with pytest.raises(Exception, match="mock open"):
            run0edit.get_editor_path_from_conf("/some/other/path.conf")
        mock_open.assert_called_once_with("/some/other/path.conf", encoding=mock.ANY)

    def test_read_conf_path_valid(self):
        """Should read and validate editor path from conf file"""
        conf = new_test_file(b"/bin/true\n")
        editor = run0edit.get_editor_path_from_conf(conf)
        assert editor == "/bin/true"
        remove_test_file(conf)

    def test_read_conf_path_valid_with_comment(self):
        """Should read and validate editor path from conf file, ignoring comment lines"""
        conf = new_test_file(b"# this is a comment\n/bin/true \n")
        editor = run0edit.get_editor_path_from_conf(conf)
        assert editor == "/bin/true"
        remove_test_file(conf)

    def test_read_conf_path_empty(self):
        """Should ignore empty conf file"""
        conf = new_test_file(b"")
        assert run0edit.get_editor_path_from_conf(conf) is None
        remove_test_file(conf)

    def test_read_conf_path_only_comments(self):
        """Should ignore empty conf file"""
        conf = new_test_file(b"# this is a comment\n  # another comment\n")
        assert run0edit.get_editor_path_from_conf(conf) is None
        remove_test_file(conf)

    def test_read_conf_path_invalid(self):
        """Should read and reject bad editor path from conf file"""
        conf = new_test_file(b"/dev/null")
        with pytest.raises(run0edit.InvalidEditorConfError):
            run0edit.get_editor_path_from_conf(conf)
        remove_test_file(conf)

    def test_read_missing_conf_file(self):
        """Should skip over missing conf file"""
        conf = new_test_file()
        remove_test_file(conf)
        assert run0edit.get_editor_path_from_conf(conf) is None

    @mock.patch("run0edit_main.open", create=True)
    def test_unreadable_conf_file(self, mock_open):
        """Should raise error if conf file exists but is unreadable"""
        mock_open.side_effect = PermissionError
        with pytest.raises(run0edit.UnreadableEditorConfError):
            run0edit.get_editor_path_from_conf()


@mock.patch.dict("os.environ", {}, clear=True)
@mock.patch("shutil.which")
class TestGetEditorPathFromEnv(unittest.TestCase):
    """Tests for get_editor_path_from_env"""

    def test_empty_env(self, mock_which):
        """Should return None if environment is empty"""
        assert run0edit.get_editor_path_from_env() is None
        mock_which.assert_not_called()

    @mock.patch.dict("os.environ", {"VISUAL": "/visual-editor"})
    def test_visual_valid(self, mock_which):
        """Should return valid editor found in VISUAL"""
        mock_which.side_effect = lambda s: s
        assert run0edit.get_editor_path_from_env() == "/visual-editor"
        mock_which.assert_called_once_with("/visual-editor")

    @mock.patch.dict("os.environ", {"VISUAL": "relative-editor"})
    def test_relative_visual_valid(self, mock_which):
        """Should return valid relative editor found in VISUAL"""
        mock_which.side_effect = lambda s: f"/usr/bin/{s}"
        assert run0edit.get_editor_path_from_env() == "/usr/bin/relative-editor"
        mock_which.assert_called_once_with("relative-editor")

    @mock.patch.dict("os.environ", {"VISUAL": "/invalid"})
    def test_visual_invalid(self, mock_which):
        """Should not return invalid editor found in VISUAL"""
        mock_which.return_value = None
        assert run0edit.get_editor_path_from_env() is None
        mock_which.assert_called_once_with("/invalid")

    @mock.patch.dict("os.environ", {"EDITOR": "/editor"})
    def test_editor_valid(self, mock_which):
        """Should return valid editor found in EDITOR"""
        mock_which.side_effect = lambda s: s
        assert run0edit.get_editor_path_from_env() == "/editor"
        mock_which.assert_called_once_with("/editor")

    @mock.patch.dict("os.environ", {"EDITOR": "/invalid"})
    def test_editor_invalid(self, mock_which):
        """Should not return invalid editor found in EDITOR"""
        mock_which.return_value = None
        assert run0edit.get_editor_path_from_env() is None
        mock_which.assert_called_once_with("/invalid")

    @mock.patch.dict("os.environ", {"VISUAL": "/visual", "EDITOR": "/editor"})
    def test_visual_preferred_over_editor(self, mock_which):
        """Should prefer editor in VISUAL over editor in EDITOR"""
        mock_which.side_effect = lambda s: s
        assert run0edit.get_editor_path_from_env() == "/visual"
        mock_which.assert_called_once_with("/visual")

    @mock.patch.dict("os.environ", {"VISUAL": "/visual", "EDITOR": "/editor"})
    def test_valid_editor_invalid_visual(self, mock_which):
        """Should fall back to editor in EDITOR if editor in VISUAL is invalid"""
        mock_which.side_effect = [None, "/editor"]
        assert run0edit.get_editor_path_from_env() == "/editor"
        assert mock_which.call_args_list == [mock.call("/visual"), mock.call("/editor")]


class TestGetFallbackEditorPath(unittest.TestCase):
    """Tests for get_fallback_editor_path"""

    @mock.patch("run0edit_main.find_command")
    def test_default_fallbacks(self, mock_find_cmd):
        """
        Should try to find expected default fallback editors, and return None if none found
        """
        mock_find_cmd.side_effect = run0edit.CommandNotFoundError
        assert run0edit.get_fallback_editor_path() is None
        expected = ("nano", "vi")
        assert mock_find_cmd.call_args_list == [mock.call(cmd) for cmd in expected]

    def test_provided_fallbacks(self):
        """Should return first fallback editor that is a valid command"""
        fallbacks = ("nonexistent-cmd-asdf", "", "true")
        editor = run0edit.get_fallback_editor_path(fallbacks=fallbacks)
        assert editor in ("/bin/true", "/usr/bin/true")


@mock.patch("run0edit_main.get_fallback_editor_path")
@mock.patch("run0edit_main.get_editor_path_from_env")
@mock.patch("run0edit_main.get_editor_path_from_conf")
class TestGetEditorPath(unittest.TestCase):
    """Tests for get_editor_path"""

    def test_valid_provided(self, mock_from_conf, mock_from_env, mock_fallback):
        """Should return provided editor path if valid"""
        editor = run0edit.get_editor_path("/bin/true")
        assert editor == os.path.realpath("/bin/true")
        mock_from_conf.assert_not_called()
        mock_from_env.assert_not_called()
        mock_fallback.assert_not_called()

    def test_invalid_provided(self, mock_from_conf, mock_from_env, mock_fallback):
        """Should raise exception if provided invalid editor path"""
        with pytest.raises(run0edit.InvalidProvidedEditorError, match="/dev/null"):
            run0edit.get_editor_path("/dev/null")
        mock_from_conf.assert_not_called()
        mock_from_env.assert_not_called()
        mock_fallback.assert_not_called()

    def test_gets_from_conf_if_not_provided(self, mock_from_conf, mock_from_env, mock_fallback):
        """Should get editor from environment if not provided"""
        editor = mock.sentinel.editor_from_conf
        mock_from_conf.return_value = editor
        assert run0edit.get_editor_path() == editor
        mock_from_conf.assert_called_once_with()
        mock_from_env.assert_not_called()
        mock_fallback.assert_not_called()

    def test_gets_from_env_if_not_from_conf(self, mock_from_conf, mock_from_env, mock_fallback):
        """Should get editor from environment if not provided or found in conf file"""
        editor = mock.sentinel.editor_from_env
        mock_from_conf.return_value = None
        mock_from_env.return_value = editor
        assert run0edit.get_editor_path() == editor
        mock_from_conf.assert_called_once_with()
        mock_from_env.assert_called_once_with()
        mock_fallback.assert_not_called()

    def test_gets_fallback_if_no_conf(self, mock_from_conf, mock_from_env, mock_fallback):
        """Should get editor from conf file if not provided"""
        editor = mock.sentinel.fallback_editor
        mock_from_conf.return_value = None
        mock_from_env.return_value = None
        mock_fallback.return_value = editor
        assert run0edit.get_editor_path() == editor
        mock_from_conf.assert_called_once_with()
        mock_from_env.assert_called_once_with()
        mock_fallback.assert_called_once_with()

    def test_no_conf_no_fallback(self, mock_from_conf, mock_from_env, mock_fallback):
        """Should raise expected error if fallback fails to find editor"""
        mock_from_env.return_value = None
        mock_from_conf.return_value = None
        mock_fallback.return_value = None
        with pytest.raises(run0edit.EditorNotFoundError):
            run0edit.get_editor_path()
        mock_from_conf.assert_called_once_with()
        mock_from_env.assert_called_once_with()
        mock_fallback.assert_called_once_with()


@mock.patch("run0edit_main.get_editor_path")
class TestHandleEditorSelection(unittest.TestCase):
    """Tests for handle_editor_selection"""

    def test_check_args(self, mock_get_editor):
        """Should pass argument to get_editor_path and return its return value"""
        mock_get_editor.return_value = mock.sentinel.editor_path
        provided = mock.sentinel.provided
        editor = run0edit.handle_editor_selection(provided_editor=provided)
        assert editor == mock.sentinel.editor_path
        mock_get_editor.assert_called_once_with(provided_editor=provided)

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_handle_errors(self, mock_stderr, mock_get_editor):
        """Should print expected messages in response to errors"""
        error_patterns: dict[type[run0edit.EditorSelectionError], str] = {
            run0edit.EditorNotFoundError: r"^run0edit: Editor not found\. Please install either ",
            run0edit.UnreadableEditorConfError: r" Configuration file exists but is unreadable\.",
            run0edit.InvalidEditorConfError: r"^run0edit: Configuration file has an invalid ",
            run0edit.InvalidProvidedEditorError: r"^run0edit: --editor must be an absolute path ",
        }
        mock_get_editor.side_effect = iter(error_patterns)
        for err, pattern in error_patterns.items():
            with pytest.raises(err):
                run0edit.handle_editor_selection()
            assert re.search(pattern, mock_stderr.getvalue())
            mock_stderr.truncate(0)
            mock_stderr.seek(0)


class TestPathExists(unittest.TestCase):
    """Tests for PathExists enum"""

    def test_variants(self):
        """Should have expected variants"""
        assert set(run0edit.PathExists) == {
            run0edit.PathExists.YES,
            run0edit.PathExists.NO,
            run0edit.PathExists.MAYBE,
        }

    def test_from_bool(self):
        """from_bool method should give expected values"""
        assert run0edit.PathExists.from_bool(True) == run0edit.PathExists.YES
        assert run0edit.PathExists.from_bool(False) == run0edit.PathExists.NO


class TestCheckDirectoryExistence(unittest.TestCase):
    """Tests for check_directory_existence"""

    def setUp(self):
        """Set up test directory"""
        self.test_dir = new_test_dir()

    def tearDown(self):
        """Remove test directory"""
        remove_test_dir(self.test_dir)

    def test_fs_root(self):
        """Should return YES for filesystem root /"""
        assert run0edit.check_directory_existence("/") == run0edit.PathExists.YES

    def test_exists(self):
        """Should return YES when directory exists, whether or not path itself exists"""
        file = f"{self.test_dir}/foo.txt"
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.YES
        pathlib.Path(file).touch()
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.YES

    def test_unreadable_final_dir(self):
        """Should return YES when directory exists, even if contents are inaccessible"""
        file = f"{self.test_dir}/foo.txt"
        os.chmod(self.test_dir, 0o000)
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.YES
        os.chmod(self.test_dir, 0o700)

    def test_unreadable_middle_dir(self):
        """Should return MAYBE if unable to check directory existence"""
        file = f"{self.test_dir}/foo/bar.txt"
        os.chmod(self.test_dir, 0o000)
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.MAYBE
        os.chmod(self.test_dir, 0o400)
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.NO
        os.chmod(self.test_dir, 0o700)

    def test_unreadable_subdir(self):
        """
        Should return MAYBE if missing executable bit on directory prevents
        checking directory existence.
        """
        os.mkdir(f"{self.test_dir}/foo")
        file = f"{self.test_dir}/foo/bar/spam.txt"
        os.chmod(self.test_dir, 0o600)
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.MAYBE
        os.chmod(self.test_dir, 0o700)

    def test_not_directory_intermediate(self):
        """Should return NO if file encountered where directory should be"""
        pathlib.Path(f"{self.test_dir}/foo").touch()
        file = f"{self.test_dir}/foo/bar/spam.txt"
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.NO

    def test_not_directory_final(self):
        """Should return NO if parent is file instead of directory"""
        pathlib.Path(f"{self.test_dir}/foo").touch()
        file = f"{self.test_dir}/foo/bar.txt"
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.NO

    def test_unknown_parent_type(self):
        """Should return MAYBE if parent exists but unable to determine if it's a directory"""
        os.mkdir(f"{self.test_dir}/foo")
        file = f"{self.test_dir}/foo/bar.txt"
        os.chmod(self.test_dir, 0o600)
        assert run0edit.check_directory_existence(file) == run0edit.PathExists.MAYBE
        os.chmod(self.test_dir, 0o700)


class TestTempFile(unittest.TestCase):
    """Tests for TempFile class"""

    def setUp(self):
        """Set up temp files"""
        self.empty_file = run0edit.TempFile("empty")
        self.non_empty_file = run0edit.TempFile("non-empty")
        with open(self.non_empty_file.path, "wb") as f:
            f.write(b"asdf")

    def tearDown(self):
        """Clean up temp files"""
        for temp_file in (self.empty_file, self.non_empty_file):
            try:
                shutil.rmtree(temp_file.directory)
            except OSError:
                pass

    def test_temp_file(self):
        """
        Should create temp file with name derived from given path, and remove
        it when .remove() is called.
        """
        filename = "spam.txt"
        path = f"/foo/bar/{filename}"
        temp = run0edit.TempFile(path)
        temp_dir = os.path.dirname(temp.path)
        assert temp_dir == temp.directory
        assert os.path.basename(temp_dir).startswith("run0edit-")
        assert len(temp_dir.removeprefix("run0edit-")) >= 8
        temp_filename = os.path.basename(temp.path)
        assert temp_filename == filename
        assert os.path.isfile(temp.path)
        assert os.path.getsize(temp.path) == 0
        temp.remove()
        assert not os.path.exists(temp_dir)

    def test_long_filename(self):
        """Should truncate long filenames"""
        filename = "long" * 100
        temp = run0edit.TempFile(filename)
        assert len(os.path.basename(temp.path)) < 100
        temp.remove()

    def test_remove_unconditional(self):
        """Should remove temp file unconditionally by default"""
        self.empty_file.remove()
        assert not os.path.exists(self.empty_file.path)
        self.non_empty_file.remove()
        assert not os.path.exists(self.non_empty_file.path)

    def test_remove_only_if_empty(self):
        """Should only remove empty temp files with option passed"""
        self.empty_file.remove(only_if_empty=True)
        assert not os.path.exists(self.empty_file.path)
        self.non_empty_file.remove(only_if_empty=True)
        assert os.path.exists(self.non_empty_file.path)

    @mock.patch("os.rmdir")
    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_remove_fail(self, mock_stderr, mock_rmdir):
        """Should report error message if removing temp dir fails"""
        mock_rmdir.side_effect = OSError("mock rmdir error")
        self.empty_file.remove()
        assert "run0edit: Warning: failed to remove temporary directory " in mock_stderr.getvalue()
        assert not os.path.exists(self.empty_file.path)


@mock.patch("run0edit_main.find_command")
class TestRun0Arguments(unittest.TestCase):
    """Tests for Run0Arguments class"""

    def test_argument_list(self, mock_find_cmd):
        """Should build expected argument list"""
        mock_find_cmd.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        run0_args = run0edit.Run0Arguments(
            description="Description of program",
            systemd_properties=["foo", "bar"],
            command="emacs",
            command_args=["spam", "spamspam", "spam spam spam"],
        )
        expected_args = [
            "/usr/bin/run0",
            "--description=Description of program",
            "--property=foo",
            "--property=bar",
            "--",
            "emacs",
            "spam",
            "spamspam",
            "spam spam spam",
        ]
        assert run0_args.argument_list() == expected_args
        mock_find_cmd.assert_called_once_with("run0")


@mock.patch("run0edit_main.find_command")
class TestBuildRun0Arguments(unittest.TestCase):
    """Tests for build_run0_arguments"""

    @staticmethod
    def mock_cmd_not_found(not_found_cmd: str) -> Callable[[str], str]:
        """Mock function to emulate a command not being found."""

        def _mock_cmd_not_found_inner(cmd: str) -> str:
            if cmd == not_found_cmd:
                raise run0edit.CommandNotFoundError(cmd)
            return f"/usr/bin/{cmd}"

        return _mock_cmd_not_found_inner

    def test_run0_not_found(self, mock_find_cmd):
        """Should raise exception if run0 not found"""
        mock_find_cmd.side_effect = self.mock_cmd_not_found("run0")
        with pytest.raises(run0edit.CommandNotFoundError, match="run0"):
            run0edit.build_run0_arguments("foo", "bar", "baz")

    def test_python3_not_found(self, mock_find_cmd):
        """Should raise exception if python3 not found"""
        mock_find_cmd.side_effect = self.mock_cmd_not_found("python3")
        with pytest.raises(run0edit.CommandNotFoundError, match="python3"):
            run0edit.build_run0_arguments("foo", "bar", "baz")

    def test_args(self, mock_find_cmd):
        """Should return expected arguments"""
        mock_find_cmd.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        path = new_test_file()
        temp_path = "/path/to/temp/file"
        editor = "/usr/bin/vim"
        args = run0edit.build_run0_arguments(path, temp_path, editor)
        props = run0edit.SYSTEMD_SANDBOX_PROPERTIES
        assert args.systemd_properties == props
        assert args.description.startswith("run0edit ")
        assert args._run0_cmd == "/usr/bin/run0"
        assert args.extra_options == []
        assert args.command == "/usr/bin/python3"
        assert args.command_args == [run0edit.INNER_SCRIPT_PATH, path, temp_path, editor]
        assert len(args.argument_list()) == len(props) + 8
        remove_test_file(path)

    def test_args_bgcolor(self, mock_find_cmd):
        """Should return expected arguments"""
        mock_find_cmd.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        path = new_test_file()
        temp_path = "/path/to/temp/file"
        editor = "/usr/bin/vim"
        args = run0edit.build_run0_arguments(path, temp_path, editor, bgcolor="bgcolor")
        props = run0edit.SYSTEMD_SANDBOX_PROPERTIES
        assert args.systemd_properties == props
        assert args.description.startswith("run0edit ")
        assert args._run0_cmd == "/usr/bin/run0"
        assert args.extra_options == ["--background=bgcolor"]
        assert args.command == "/usr/bin/python3"
        assert args.command_args == [run0edit.INNER_SCRIPT_PATH, path, temp_path, editor]
        assert len(args.argument_list()) == len(props) + 9
        remove_test_file(path)

    def test_debug_arg(self, mock_find_cmd):
        """Should set environment variable with debug option"""
        mock_find_cmd.side_effect = lambda cmd: cmd
        args_debug = run0edit.build_run0_arguments("foo", "bar", "baz", debug=True)
        assert "--setenv=RUN0EDIT_DEBUG=1" in args_debug.argument_list()

    def test_no_prompt_arg(self, mock_find_cmd):
        """Should set environment variable with no_prompt option"""
        mock_find_cmd.side_effect = lambda cmd: cmd
        args_debug = run0edit.build_run0_arguments("foo", "bar", "baz", no_prompt=True)
        assert "--setenv=RUN0EDIT_NO_PROMPT=1" in args_debug.argument_list()


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
        with pytest.raises(run0edit.InvalidPathError, match=r"/var is a directory\."):
            run0edit.validate_path("/var")

    def test_user_writable(self):
        """Should fail if path is writable by current user"""
        os.chmod(self.path, 0o600)
        with pytest.raises(
            run0edit.InvalidPathError,
            match=f"{self.path} is writable by the current user; run0edit is unnecessary.",
        ):
            run0edit.validate_path(self.path)

    @mock.patch("run0edit_main.readonly_filesystem")
    def test_readonly(self, mock_ro_fs):
        """Should fail if path is on read-only filesystem"""
        mock_ro_fs.return_value = True
        with pytest.raises(
            run0edit.InvalidPathError, match=f"{self.path} is on a read-only filesystem."
        ):
            run0edit.validate_path(self.path)
        mock_ro_fs.assert_called_once_with(self.path)

    @mock.patch("run0edit_main.readonly_filesystem")
    def test_readonly_directory(self, mock_ro_fs):
        """Should fail if directory is on read-only filesystem"""
        mock_ro_fs.side_effect = [None, True]
        with pytest.raises(
            run0edit.InvalidPathError, match=f"{self.path} is on a read-only filesystem."
        ):
            run0edit.validate_path(self.path)
        assert mock_ro_fs.call_args_list == [
            mock.call(self.path),
            mock.call(os.path.dirname(self.path)),
        ]

    def test_path_does_not_exist(self):
        """Should fail if directory does not exist"""
        with pytest.raises(run0edit.InvalidPathError, match=f"No such directory {self.path}-dir"):
            run0edit.validate_path(f"{self.path}-dir/foo.txt")

    def test_success(self):
        """Should succeed (returning None) if path is valid"""
        run0edit.validate_path(self.path)


@mock.patch("os.execv")
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
    def test_validates_path_succeeded(self, mock_validate, mock_execv):
        """Should validate path and continue if valid"""
        mock_validate.return_value = None
        run0edit.run(self.path, "...")
        mock_validate.assert_called_once_with(self.path)
        mock_execv.assert_called_once()

    @mock.patch("run0edit_main.print_err")
    @mock.patch("run0edit_main.validate_path")
    def test_path_validation_failed(self, mock_validate, mock_print_err, mock_execv):
        """Should validate path and exit with an error message if not valid"""
        mock_validate.side_effect = run0edit.InvalidPathError("some error message")
        assert run0edit.run(self.path, "...") == 1
        mock_validate.assert_called_once_with(self.path)
        mock_print_err.assert_called_once_with("some error message")
        mock_execv.assert_not_called()

    def test_check_args(self, mock_execv):
        """Should pass expected arguments to os.execv"""
        editor = "/usr/sbin/butterfly"
        run0edit.run(self.path, editor)
        mock_execv.assert_called_once_with("/usr/bin/run0", mock.ANY)
        args = mock_execv.call_args.args[1]
        temp_filename = args[-2]
        expected_args = run0edit.build_run0_arguments(self.path, temp_filename, editor)
        assert args == expected_args.argument_list()

    @staticmethod
    def mock_editor_process(_path: str, args: Sequence[str], **_: Any) -> int:
        """Mock os.execv that writes text to temp file"""
        with open(args[-2], "w", encoding="utf8") as f:
            f.write(os.environ["MOCK_TEXT"])
        return int(os.environ["MOCK_RETCODE"])

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_run_success(self, mock_stderr, mock_execv):
        """Should clean up temp file and return 0 if execv succeeds"""
        mock_execv.side_effect = self.mock_editor_process
        with mock.patch.dict("os.environ", {"MOCK_TEXT": "foo", "MOCK_RETCODE": "0"}):
            assert run0edit.run(self.path, "...") == 0
        mock_execv.assert_called_once_with("/usr/bin/run0", mock.ANY)
        temp_filename = mock_execv.call_args.args[1][-2]
        assert not os.path.exists(temp_filename)
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_execv_fail(self, mock_stderr, mock_execv):
        """Should return 1 and clean empty tempfile if execv fails"""
        mock_execv.side_effect = OSError("mock execv error")
        assert run0edit.run(self.path, "...") == 1
        mock_execv.assert_called_once_with("/usr/bin/run0", mock.ANY)
        temp_filename = mock_execv.call_args.args[0][-2]
        assert not os.path.exists(temp_filename)
        assert mock_stderr.getvalue() == "run0edit: Warning: execution of run0 failed\n"


class TestAnsiColor(unittest.TestCase):
    """Tests for ansi_color"""

    def test_valid_codes(self):
        """The empty string and numbers separated by ; should be accepted"""
        test_values = ("", "0123456789", "44;5", "1;2;3", "0;0;0;0;0;0;0")
        for value in test_values:
            assert run0edit.ansi_color(value) == value, f"valid ANSI code {value} was rejected"

    def test_invalid_codes(self):
        """Various other values should be rejected with ValueError"""
        test_values = (
            " ",
            "0 ",
            ";",
            "bad",
            "0asdf1",
            "1;2;3;",
            ";40",
            "\u00b2",  # SUPERSCRIPT TWO
            "\u00bd",  # VULGAR FRACTION ONE HALF
            "\u1369",  # ETHIOPIC DIGIT ONE
            "\u2160",  # ROMAN NUMERAL ONE
            "\u2468",  # CIRCLED DIGIT NINE
        )
        for value in test_values:
            with pytest.raises(ValueError):
                run0edit.ansi_color(value)


@mock.patch("sys.stderr", new_callable=io.StringIO)
@mock.patch("sys.stdout", new_callable=io.StringIO)
class TestParseArguments(unittest.TestCase):
    """Tests for parse_arguments"""

    USAGE_TEXT: str = """
    usage: run0edit [-h] [-v] [--editor EDITOR] [--background COLOR] [--no-prompt] FILE [FILE ...]
    """.strip()
    DESCRIPTION: str = "run0edit allows a permitted user to edit a file as root."

    @mock.patch("sys.argv", [])
    def test_no_args(self, mock_stdout, mock_stderr):
        """Should show usage and exit with code 2 if no arguments passed"""
        with pytest.raises(SystemExit, match="2"):
            run0edit.parse_arguments()
        assert mock_stdout.getvalue() == ""
        msg = re.sub(r"\s+", " ", mock_stderr.getvalue().strip())
        error_text = "run0edit: error: the following arguments are required: FILE"
        assert msg == f"{self.USAGE_TEXT} {error_text}"

    @mock.patch("sys.argv", ["run0edit", "--help"])
    def test_help(self, mock_stdout, mock_stderr):
        """Should show usage and exit normally if called with -h or --help"""
        with pytest.raises(SystemExit, match="0"):
            run0edit.main()
        help_text = re.sub(r"\s+", " ", mock_stdout.getvalue().strip())
        assert help_text.startswith(f"{self.USAGE_TEXT} {self.DESCRIPTION}")
        mock_stdout.truncate(0)
        mock_stdout.seek(0)
        with (
            mock.patch("sys.argv", ["run0edit", "-h"]),
            pytest.raises(SystemExit, match="0"),
        ):
            run0edit.main()
        short_help_text = re.sub(r"\s+", " ", mock_stdout.getvalue().strip())
        assert short_help_text == help_text
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--version"])
    def test_version(self, mock_stdout, mock_stderr):
        """Should show version and exit normally if called with -v or --version"""
        with pytest.raises(SystemExit, match="0"):
            run0edit.parse_arguments()
        expected_version_text = f"run0edit {run0edit.__version__}\n"
        assert mock_stdout.getvalue() == expected_version_text
        mock_stdout.truncate(0)
        mock_stdout.seek(0)
        with (
            mock.patch("sys.argv", ["run0edit", "-v"]),
            pytest.raises(SystemExit, match="0"),
        ):
            run0edit.main()
        assert mock_stdout.getvalue() == expected_version_text
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--editor=/path/to/editor", "foo"])
    def test_editor(self, mock_stdout, mock_stderr):
        """Should accept and store --editor argument"""
        args = run0edit.parse_arguments()
        assert args.editor == "/path/to/editor"
        assert args.background is None
        assert not args.debug
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--background=1;2;3", "foo"])
    def test_background(self, mock_stdout, mock_stderr):
        """Should accept and store --editor argument"""
        args = run0edit.parse_arguments()
        assert args.editor is None
        assert args.background == "1;2;3"
        assert not args.debug
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--background=", "foo"])
    def test_empty_background(self, mock_stdout, mock_stderr):
        """Should accept and store --editor argument"""
        args = run0edit.parse_arguments()
        assert args.editor is None
        assert args.background == ""
        assert not args.debug
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--background=bad", "foo"])
    def test_invalid_background(self, mock_stdout, mock_stderr):
        """Should accept and store --editor argument"""
        with pytest.raises(SystemExit, match="2"):
            run0edit.parse_arguments()
        assert mock_stdout.getvalue() == ""
        assert "argument --background: invalid ansi_color value: 'bad'" in mock_stderr.getvalue()

    @mock.patch("sys.argv", ["run0edit", "--debug", "foo"])
    def test_debug(self, mock_stdout, mock_stderr):
        """Should recognize --debug argument"""
        args = run0edit.parse_arguments()
        assert args.editor is None
        assert args.debug
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "foo", "bar", "baz"])
    def test_multiple_paths(self, mock_stdout, mock_stderr):
        """Should accept multiple paths"""
        args = run0edit.parse_arguments()
        assert args.paths == ["foo", "bar", "baz"]
        assert args.editor is None
        assert not args.debug
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""


@mock.patch("sys.stderr", new_callable=io.StringIO)
@mock.patch("sys.stdout", new_callable=io.StringIO)
class TestCatchUsageMistake(unittest.TestCase):
    """Tests for catch_usage_mistake"""

    FIRST_PATH: str = "sh"

    def test_no_prompt(self, mock_stdout, mock_stderr):
        """Should do nothing with prompt=False"""
        run0edit.catch_usage_mistake([self.FIRST_PATH, "asdf"], prompt=False)
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    def test_one_path(self, mock_stdout, mock_stderr):
        """Should do nothing if only one path"""
        run0edit.catch_usage_mistake([self.FIRST_PATH], prompt=True)
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    def test_path_sep_in_first_path(self, mock_stdout, mock_stderr):
        """Should do nothing if path separator in first path"""
        run0edit.catch_usage_mistake([f"./{self.FIRST_PATH}", "asdf"], prompt=True)
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    def test_first_path_not_command(self, mock_stdout, mock_stderr):
        """Should do nothing if first path does not resolve to command"""
        run0edit.catch_usage_mistake(["thisisnotacommand", "asdf"], prompt=True)
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("run0edit_main.input", create=True)
    def test_first_path_is_command_response_yes(self, mock_input, mock_stdout, mock_stderr):
        """
        Should print warning message and prompt for user input, returning normally if
        user response is "yes"
        """
        mock_input.return_value = "yes"
        run0edit.catch_usage_mistake([self.FIRST_PATH, "asdf"], prompt=True)
        mock_input.assert_called_once_with(
            f"\nDo you really want to edit the file ./{self.FIRST_PATH}? [y/N] "
        )
        assert mock_stdout.getvalue() == ""
        assert (
            f"Warning: `{self.FIRST_PATH}` looks like an executable command. "
            in mock_stderr.getvalue()
        )

    @mock.patch("run0edit_main.input", create=True)
    def test_first_path_is_command_response_no(self, mock_input, mock_stdout, mock_stderr):
        """Should raise expected exception if user gives empty/negative response"""
        mock_input.return_value = ""
        with pytest.raises(run0edit.UsageError):
            run0edit.catch_usage_mistake([self.FIRST_PATH, "asdf"], prompt=True)
        mock_input.assert_called_once()
        assert mock_stdout.getvalue() == ""
        assert (
            f"Warning: `{self.FIRST_PATH}` looks like an executable command. "
            in mock_stderr.getvalue()
        )


@mock.patch.dict("os.environ", {}, clear=True)
@mock.patch("sys.stderr", new_callable=io.StringIO)
@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_main.run")
class TestMain(unittest.TestCase):
    """Tests for main"""

    @mock.patch("run0edit_main.parse_arguments")
    def test_parses_arguments(self, mock_parse_args, mock_run, mock_stdout, mock_stderr):
        """Should call parse_arguments"""
        mock_parse_args.side_effect = Exception("mock parse_arguments")
        with pytest.raises(Exception, match="mock parse_arguments"):
            run0edit.main()
        mock_parse_args.assert_called_once_with()
        mock_run.assert_not_called()
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--editor=/bin/true", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script")
    def test_valid_inner_script(self, mock_validate, mock_run, mock_stdout, mock_stderr):
        """Should continue to rest of function if validate_inner_script succeeds"""
        mock_validate.return_value = True
        run0edit.main()
        mock_validate.assert_called_once()
        mock_run.assert_called_once()
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script")
    def test_invalid_inner_script(self, mock_validate, mock_run, mock_stdout, mock_stderr):
        """Should fail with expected error if validate_inner_script fails"""
        mock_validate.return_value = False
        assert run0edit.main() == 1
        mock_validate.assert_called_once()
        mock_run.assert_not_called()
        assert mock_stdout.getvalue() == ""
        assert re.search(
            "^run0edit: ERROR: Inner script was not found .* or did not have expected BLAKE2 hash",
            mock_stderr.getvalue().replace("\n", " "),
        )

    @mock.patch("sys.argv", ["run0edit", "nano", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.catch_usage_mistake")
    def test_catches_usage_mistake(self, mock_catch_usage, mock_run, mock_stdout, mock_stderr):
        """Should return 2 if usage error reported"""
        mock_catch_usage.side_effect = run0edit.UsageError
        assert run0edit.main() == 2
        mock_catch_usage.assert_called_once_with(["nano", "asdf"], prompt=True)
        mock_run.assert_not_called()
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--editor=/usr/bin/butterfly", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.get_editor_path_from_conf")
    @mock.patch("shutil.which")
    def test_valid_editor(self, mock_which, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should use valid editor passed as command-line argument"""
        mock_which.side_effect = lambda s: s
        run0edit.main()
        mock_which.assert_called_once_with("/usr/bin/butterfly")
        mock_editor_path.assert_not_called()
        assert mock_run.call_args.args == ("asdf", "/usr/bin/butterfly")
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--editor=/etc/hosts", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.get_editor_path_from_conf")
    @mock.patch("shutil.which")
    def test_invalid_editor(self, mock_which, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should fail if invalid editor passed as command-line argument"""
        mock_which.return_value = None
        assert run0edit.main() == 1
        mock_which.assert_called_once_with("/etc/hosts")
        mock_editor_path.assert_not_called()
        mock_run.assert_not_called()
        assert mock_stdout.getvalue() == ""
        assert (
            mock_stderr.getvalue()
            == "run0edit: --editor must be an absolute path to an executable file\n"
        )

    @mock.patch("sys.argv", ["run0edit", "asdf"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.get_editor_path_from_conf")
    def test_editor_not_found(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should fail with expected message if unable to find editor"""
        mock_editor_path.side_effect = run0edit.EditorNotFoundError
        assert run0edit.main() == 1
        mock_run.assert_not_called()
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue().startswith("run0edit: Editor not found.")

    @mock.patch("sys.argv", ["run0edit", "path1", "path2"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.get_editor_path_from_conf")
    def test_successful_run(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should pass expected arguments to run and exit successfully"""
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.return_value = 0
        assert run0edit.main() == 0
        paths = ("path1", "path2")
        assert mock_run.call_args_list == [
            mock.call(path, editor, bgcolor=None, debug=False, no_prompt=False) for path in paths
        ]
        mock_editor_path.assert_called_once()
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "--background=1;2;3", "path1", "path2"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.get_editor_path_from_conf")
    def test_run_with_bgcolor(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should pass bgcolor argument to run and exit successfully"""
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.return_value = 0
        assert run0edit.main() == 0
        paths = ("path1", "path2")
        assert mock_run.call_args_list == [
            mock.call(path, editor, bgcolor="1;2;3", debug=False, no_prompt=False) for path in paths
        ]
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "path1", "path2", "path3"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.get_editor_path_from_conf")
    def test_failed_run(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should return as soon as a run returns nonzero"""
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.side_effect = [0, 42, 0]
        assert run0edit.main() == 42
        assert mock_run.call_count == 2
        assert mock_run.call_args.args == ("path2", editor)
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == ""

    @mock.patch("sys.argv", ["run0edit", "example/path"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.get_editor_path_from_conf")
    def test_missing_command(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """Should return 1 if command missing"""
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.side_effect = run0edit.CommandNotFoundError("foo")
        assert run0edit.main() == 1
        mock_run.assert_called_once()
        assert mock_run.call_args.args == ("example/path", editor)
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == "run0edit: command `foo` not found\n"

    @mock.patch("sys.argv", ["run0edit", "--debug", "example/path"])
    @mock.patch("run0edit_main.validate_inner_script", lambda: True)
    @mock.patch("run0edit_main.get_editor_path_from_conf")
    def test_missing_command_debug(self, mock_editor_path, mock_run, mock_stdout, mock_stderr):
        """
        In debug mode, should pass debug argument to `run`, and raise expected
        error if command missing.
        """
        editor = "/usr/bin/vim"
        mock_editor_path.return_value = editor
        mock_run.side_effect = run0edit.CommandNotFoundError("foo")
        with pytest.raises(run0edit.CommandNotFoundError, match="foo"):
            run0edit.main()
        mock_run.assert_called_once_with(
            "example/path", editor, bgcolor=None, debug=True, no_prompt=False
        )
        assert mock_stdout.getvalue() == ""
        assert mock_stderr.getvalue() == "run0edit: command `foo` not found\n"
