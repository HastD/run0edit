#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Unit tests for run0edit_inner.py"""

import getpass
import hashlib
import io
import os
import re
import subprocess
import unittest
from pathlib import Path
from typing import Final
from unittest import mock

import pytest

import run0edit_inner as inner

from . import new_test_dir, new_test_file, remove_test_dir

MY_UID: Final[int] = os.getuid()
MY_GID: Final[int] = os.getgid()

# This is actually the flag for FS_NODUMP_FL. We use this in place of the
# real immutable flag in unit tests because it's benign and can be set by
# unprivileged users.
MOCK_IMMUTABLE_FL: Final[int] = 0x00000040


def mock_make_immutable(path: str) -> None:
    """Pretend to make the file immutable (using the NODUMP flag as a substitute)."""
    subprocess.run(["chattr", "+d", "--", path], check=True)


class TestCaseWithFiles(unittest.TestCase):
    """Base class for test cases with temp files automatically set up"""

    def setUp(self):
        """Set up test files"""
        self.target_dir = new_test_dir()
        self.target_contents = b"file contents"
        self.target_filename = new_test_file(self.target_contents, directory=self.target_dir)
        self.new_filename = f"{self.target_dir}/new-file.txt"

        self.temp_dir = new_test_dir()
        self.temp_contents = b"temp contents"
        self.temp_filename = new_test_file(self.temp_contents, directory=self.temp_dir)

        self.read_flags = os.O_CLOEXEC | os.O_NOFOLLOW | os.O_RDONLY
        self.target_dir_fd = inner.get_dir_fd(self.target_dir)
        self.target_fd = os.open(self.target_filename, self.read_flags)
        self.temp_fd = os.open(self.temp_filename, self.read_flags)

    def tearDown(self):
        """Clean up test files"""
        for fd in (self.target_dir_fd, self.target_fd, self.temp_fd):
            try:
                os.close(fd)
            except OSError:  # pragma: no cover
                pass
        remove_test_dir(self.target_dir)
        remove_test_dir(self.temp_dir)


def test_ioctl_constants():
    """Should have expected values for ioctl constants"""
    assert inner.FS_IOC_GETFLAGS == 0x80086601
    assert inner.FS_IOC_SETFLAGS == 0x40086602


@mock.patch("run0edit_inner.FS_IMMUTABLE_FL", MOCK_IMMUTABLE_FL)
class TestGetInodeFlags(TestCaseWithFiles):
    """Tests for get_inode_flags"""

    def test_mutable_file(self):
        """Non-immutable file"""
        assert inner.get_inode_flags(self.target_fd) & MOCK_IMMUTABLE_FL == 0

    def test_mutable_dir(self):
        """Non-immutable directory"""
        assert inner.get_inode_flags(self.target_dir_fd) & MOCK_IMMUTABLE_FL == 0

    def test_immutable_file(self):
        """Immutable file"""
        mock_make_immutable(self.target_filename)
        assert inner.get_inode_flags(self.target_fd) & MOCK_IMMUTABLE_FL != 0

    def test_immutable_dir(self):
        """Immutable directory"""
        mock_make_immutable(self.target_dir)
        assert inner.get_inode_flags(self.target_dir_fd) & MOCK_IMMUTABLE_FL != 0


@mock.patch("run0edit_inner.FS_IMMUTABLE_FL", MOCK_IMMUTABLE_FL)
class TestIsImmutable(TestCaseWithFiles):
    """Tests for is_immutable"""

    def test_mutable_file(self):
        """Non-immutable file"""
        assert not inner.is_immutable(self.target_fd)

    def test_mutable_dir(self):
        """Non-immutable directory"""
        assert not inner.is_immutable(self.target_dir_fd)

    def test_immutable_file(self):
        """Immutable file"""
        mock_make_immutable(self.target_filename)
        assert inner.is_immutable(self.target_fd)

    def test_immutable_dir(self):
        """Immutable directory"""
        mock_make_immutable(self.target_dir)
        assert inner.is_immutable(self.target_dir_fd)

    @mock.patch("fcntl.ioctl")
    def test_ioctl_error(self, mock_ioctl):
        """Returns false if ioctl fails"""
        mock_ioctl.side_effect = OSError
        assert not inner.is_immutable(self.target_fd)


@mock.patch("run0edit_inner.FS_IMMUTABLE_FL", MOCK_IMMUTABLE_FL)
class TestSetImmutableFlag(TestCaseWithFiles):
    """Tests for set_immutable_flag"""

    def test_set_immutable_file(self):
        """Toggle immutable flag on file"""
        fd = self.target_fd
        assert not inner.is_immutable(fd)
        inner.set_immutable_flag(fd, False)
        assert not inner.is_immutable(fd)
        inner.set_immutable_flag(fd, True)
        assert inner.is_immutable(fd)
        inner.set_immutable_flag(fd, True)
        assert inner.is_immutable(fd)
        inner.set_immutable_flag(fd, False)
        assert not inner.is_immutable(fd)

    def test_set_immutable_dir(self):
        """Toggle immutable flag on directory"""
        fd = self.target_dir_fd
        assert not inner.is_immutable(fd)
        inner.set_immutable_flag(fd, False)
        assert not inner.is_immutable(fd)
        inner.set_immutable_flag(fd, True)
        assert inner.is_immutable(fd)
        inner.set_immutable_flag(fd, True)
        assert inner.is_immutable(fd)
        inner.set_immutable_flag(fd, False)
        assert not inner.is_immutable(fd)

    @mock.patch("fcntl.ioctl")
    def test_chattr_error(self, mock_ioctl):
        """Raises expected error if ioctl fails"""
        mock_ioctl.side_effect = OSError
        with pytest.raises(inner.ChattrError):
            inner.set_immutable_flag(self.target_fd, True)


@mock.patch("run0edit_inner.input", create=True)
@mock.patch("sys.stdout", new_callable=io.StringIO)
class TestPromptRemoveImmutable(unittest.TestCase):
    """Tests for prompt_remove_immutable"""

    def test_dir(self, mock_stdout, mock_input):
        """Test answer on directory"""
        path = "/etc"
        inner.prompt_remove_immutable(path, is_dir=True)
        assert path in mock_stdout.getvalue()
        assert "directory" in mock_input.call_args.args[0]

    def test_not_dir(self, mock_stdout, mock_input):
        """Test answer on non-directory"""
        path = "/etc/hosts"
        inner.prompt_remove_immutable(path, is_dir=False)
        assert path in mock_stdout.getvalue()
        assert "directory" not in mock_input.call_args.args[0]

    def test_yes_answers(self, _, mock_input):
        """Test affirmative answers"""
        answers = ["y", "Y", "yes", "YES"]
        mock_input.side_effect = answers
        path = "/etc"
        for _ in answers:
            assert inner.prompt_remove_immutable(path, is_dir=True)

    def test_no_answers(self, _, mock_input):
        """Test negative answers"""
        answers = ["n", "", "ye", ".yes", "N", "YNO", "yyes", "nyan"]
        mock_input.side_effect = answers
        path = "/etc"
        for _ in answers:
            assert not inner.prompt_remove_immutable(path, is_dir=True)


class TestRunCommand(unittest.TestCase):
    """Tests for run_command"""

    def test_echo(self):
        """Should get correct output from echo"""
        out = inner.run_command("echo", "test", capture_output=True)
        assert out == "test\n"

    def test_not_shell(self):
        """Command should not be run as a shell"""
        out = inner.run_command("echo", ";", "echo", "foo", capture_output=True)
        assert out == "; echo foo\n"

    def test_not_captured(self):
        """Should get no output if not captured"""
        assert inner.run_command("true") is None

    def test_cmd_not_found(self):
        """Running nonexistent command should raise correct error"""
        with pytest.raises(inner.CommandNotFoundError):
            inner.run_command("this_cmd_does_not_exist")

    def test_cmd_fails(self):
        """Failed command should raise correct error"""
        with pytest.raises(inner.SubprocessError):
            inner.run_command("false")


class TestGetDirFd(TestCaseWithFiles):
    """Tests for get_dir_fd"""

    def test_open_with_dir_fd(self):
        """Can open file using dir_fd"""
        dir_fd = inner.get_dir_fd(self.target_dir)
        fd = os.open(os.path.basename(self.target_filename), flags=self.read_flags, dir_fd=dir_fd)
        inode = os.fstat(fd).st_ino
        assert inode == os.fstat(self.target_fd).st_ino


class TestGetFdForOriginal(TestCaseWithFiles):
    """Tests for check_file_exists"""

    def test_regular_file(self):
        """Should return (file fd, True) for regular file"""
        fd, exists = inner.get_fd_for_original(self.target_filename)
        assert os.fstat(fd).st_ino == os.fstat(self.target_fd).st_ino
        assert exists

    def test_directory(self):
        """Should raise NotRegularFileError for directory"""
        with pytest.raises(inner.NotRegularFileError):
            inner.get_fd_for_original(self.target_dir)

    def test_symlink_file(self):
        """Should raise NotRegularFileError for symlink to file"""
        symlink = f"{self.target_filename}-link"
        os.symlink(self.target_filename, symlink)
        with pytest.raises(inner.NotRegularFileError):
            inner.get_fd_for_original(symlink)
        os.remove(symlink)

    def test_symlink_dir(self):
        """Should raise NotRegularFileError for symlink to directory"""
        symlink = f"{self.target_dir}-link"
        os.symlink(self.target_dir, symlink)
        with pytest.raises(inner.NotRegularFileError):
            inner.get_fd_for_original(symlink)
        os.remove(symlink)

    def test_dev_file(self):
        """Should raise NotRegularFileError for device file"""
        with pytest.raises(inner.NotRegularFileError):
            inner.get_fd_for_original("/dev/null")

    def test_no_file(self):
        """Should return (dir fd, false) if file does not exist and parent is directory"""
        file = f"{self.target_dir}/foo.txt"
        fd, exists = inner.get_fd_for_original(file)
        assert os.fstat(fd).st_ino == os.fstat(self.target_dir_fd).st_ino
        assert not exists

    def test_no_directory(self):
        """Should raise NoDirectoryError if parent directory does not exist"""
        with pytest.raises(inner.NoDirectoryError, match=" does not exist"):
            inner.get_fd_for_original(os.path.join(self.target_dir, "foo/bar.txt"))

    def test_bad_directory(self):
        """Should raise NoDirectoryError if parent path is a file"""
        with pytest.raises(inner.NoDirectoryError, match=" is not a directory"):
            inner.get_fd_for_original(os.path.join(self.target_filename, "foo.txt"))

    def test_other_os_error(self):
        """Should pass through other OSError"""
        with pytest.raises(OSError):
            # We use /etc/shadow because it's unreadable by an unprivileged
            # user, which is expected for unit tests.
            inner.get_fd_for_original("/etc/shadow")


class TestCheckReadonly(TestCaseWithFiles):
    """Tests for check_readonly"""

    RO_FILE: str = "/proc/version"
    RO_DIR: str = "/proc"

    def test_writable_file(self):
        """Should return READ_WRITE for writable file"""
        assert inner.check_readonly(self.target_fd) == inner.FileStatus.READ_WRITE

    def test_writable_dir(self):
        """Should return READ_WRITE for writable directory"""
        assert inner.check_readonly(self.target_dir_fd) == inner.FileStatus.READ_WRITE

    @mock.patch("run0edit_inner.is_immutable")
    def test_immutable(self, mock_is_immutable):
        """Should return IMMUTABLE for immutable file"""
        mock_is_immutable.return_value = True
        fd = os.open(self.RO_FILE, self.read_flags)
        assert inner.check_readonly(fd) == inner.FileStatus.IMMUTABLE

    @mock.patch("run0edit_inner.readonly_filesystem")
    def test_ro_fs(self, mock_ro_fs):
        """Path on read-only filesystem should raise correct error"""
        mock_ro_fs.return_value = True
        fd = os.open(self.RO_FILE, self.read_flags)
        assert inner.check_readonly(fd) == inner.FileStatus.READ_ONLY_FS

    def test_ro_other(self):
        """Should raise expected error in other case"""
        dirfd = os.open(self.RO_DIR, self.read_flags)
        assert inner.check_readonly(dirfd) == inner.FileStatus.READ_ONLY_OTHER


@mock.patch("run0edit_inner.prompt_remove_immutable")
@mock.patch("run0edit_inner.check_readonly")
class TestHandleCheckReadonly(TestCaseWithFiles):
    """Tests for handle_check_readonly"""

    def test_check_args(self, mock_check_ro, mock_prompt):
        """Should pass expected arguments to check_readonly"""
        s = mock.sentinel
        with pytest.raises(AssertionError, match=r"^Expected code to be unreachable"):
            inner.handle_check_readonly(s.fd, s.path, prompt_immutable=s.prompt)
        mock_check_ro.assert_called_once_with(s.fd)
        mock_prompt.assert_not_called()

    def test_read_write(self, mock_check_ro, mock_prompt):
        """Should return false if file is read-write"""
        mock_check_ro.return_value = inner.FileStatus.READ_WRITE
        assert not inner.handle_check_readonly(self.target_fd, self.target_filename)
        mock_prompt.assert_not_called()

    def test_immutable_no_prompt(self, mock_check_ro, mock_prompt):
        """Should return true if file is immutable and no prompt"""
        mock_check_ro.return_value = inner.FileStatus.IMMUTABLE
        assert inner.handle_check_readonly(
            self.target_fd, self.target_filename, prompt_immutable=False
        )
        mock_prompt.assert_not_called()

    def test_immutable_file_prompt_yes(self, mock_check_ro, mock_prompt):
        """Should return true if file is immutable and user responds yes to prompt"""
        mock_check_ro.return_value = inner.FileStatus.IMMUTABLE
        mock_prompt.return_value = True
        assert inner.handle_check_readonly(
            self.target_fd, self.target_filename, prompt_immutable=True
        )
        mock_prompt.assert_called_once_with(self.target_filename, False)

    def test_immutable_dir_prompt_yes(self, mock_check_ro, mock_prompt):
        """Should return true if directory is immutable and user responds yes to prompt"""
        mock_check_ro.return_value = inner.FileStatus.IMMUTABLE
        mock_prompt.return_value = True
        assert inner.handle_check_readonly(
            self.target_dir_fd, self.target_dir, prompt_immutable=True
        )
        mock_prompt.assert_called_once_with(self.target_dir, True)

    def test_immutable_prompt_no(self, mock_check_ro, mock_prompt):
        """Should raise exception if file is immutable and user responds no to prompt"""
        mock_check_ro.return_value = inner.FileStatus.IMMUTABLE
        mock_prompt.return_value = False
        with pytest.raises(inner.ReadOnlyImmutableError):
            inner.handle_check_readonly(self.target_fd, self.target_filename, prompt_immutable=True)
        mock_prompt.assert_called_once_with(self.target_filename, False)

    def test_read_only_fs(self, mock_check_ro, mock_prompt):
        """Should raise exception if file is on read-only filesystem"""
        mock_check_ro.return_value = inner.FileStatus.READ_ONLY_FS
        with pytest.raises(inner.ReadOnlyFilesystemError):
            inner.handle_check_readonly(self.target_fd, self.target_filename)
        mock_prompt.assert_not_called()

    def test_read_only_other(self, mock_check_ro, mock_prompt):
        """Should raise exception if file is read-only for other reasons"""
        mock_check_ro.return_value = inner.FileStatus.READ_ONLY_OTHER
        with pytest.raises(inner.ReadOnlyOtherError):
            inner.handle_check_readonly(self.target_fd, self.target_filename)
        mock_prompt.assert_not_called()


class TestOpenTempFile(TestCaseWithFiles):
    """Tests for open_temp_file"""

    def test_open_read(self):
        """Should successfully open temporary file for reading"""
        fd = inner.open_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID), flags=os.O_RDONLY)
        with os.fdopen(fd, "rb") as f:
            assert f.read() == b"temp contents"

    def test_open_write(self):
        """Should successfully open temporary file for writing"""
        fd = inner.open_temp_file(
            self.temp_filename, uid_gid=(MY_UID, MY_GID), flags=os.O_WRONLY | os.O_TRUNC
        )
        with os.fdopen(fd, "wb") as f:
            f.write(b"test test")

    def test_fail_missing(self):
        """Should raise FileCopyError on bad path"""
        os.remove(self.temp_filename)
        with pytest.raises(inner.FileCopyError):
            inner.open_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID), flags=os.O_RDONLY)

    def test_fail_symlink(self):
        """Should raise FileCopyError on symlink"""
        os.remove(self.temp_filename)
        os.symlink(self.target_filename, self.temp_filename)
        with pytest.raises(inner.FileCopyError):
            inner.open_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID), flags=os.O_RDONLY)

    def test_fail_not_regular_file(self):
        """Should raise FileCopyError on non-regular file"""
        os.remove(self.temp_filename)
        os.mkfifo(self.temp_filename, mode=0o600)
        with pytest.raises(inner.FileCopyError, match="is not a regular"):
            inner.open_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID), flags=os.O_RDONLY)

    def test_fail_wrong_owner(self):
        """Should raise FileCopyError on file owned by different user"""
        with pytest.raises(inner.FileCopyError, match="owned by UID"):
            inner.open_temp_file("/etc/hostname", uid_gid=(MY_UID, MY_GID), flags=os.O_RDONLY)

    def test_fail_hardlinked(self):
        """Should raise FileCopyError on multiply-linked file"""
        os.remove(self.target_filename)
        os.link(self.temp_filename, self.target_filename)
        with pytest.raises(inner.FileCopyError, match="singly-linked"):
            inner.open_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID), flags=os.O_RDONLY)


class TestReopenFd(TestCaseWithFiles):
    """Tests for reopen_fd"""

    def test_reopen_write_only(self):
        """Should reopen fd write-only"""
        fd = self.target_fd
        inode = os.fstat(fd).st_ino
        # fd starts out unable to write
        with pytest.raises(OSError):
            os.write(fd, b"test")
        new_fd = inner.reopen_fd(fd, os.O_CLOEXEC | os.O_WRONLY | os.O_TRUNC)
        assert new_fd == fd
        assert os.fstat(new_fd).st_ino == inode
        # fd can write now
        byte_count = os.write(fd, b"test")
        assert byte_count == len(b"test")
        # fd cannot read now
        with pytest.raises(OSError):
            os.read(fd, 4)


class TestCopyFdContents(TestCaseWithFiles):
    """Tests for copy_fd_contents"""

    def test_copy(self):
        """Should copy file contents via file descriptor"""
        fd_dest = os.open(self.temp_filename, os.O_CLOEXEC | os.O_WRONLY | os.O_TRUNC)
        assert inner.copy_fd_contents(self.target_fd, fd_dest) is None
        with open(self.temp_filename, "rb") as f:
            assert f.read() == self.target_contents

    def test_checksum(self):
        """Should return checksum of written data"""
        checksum = hashlib.blake2b(self.target_contents).digest()
        fd_dest = os.open(self.temp_filename, os.O_CLOEXEC | os.O_WRONLY | os.O_TRUNC)
        assert inner.copy_fd_contents(self.target_fd, fd_dest, checksum=True) == checksum
        with open(self.temp_filename, "rb") as f:
            assert f.read() == self.target_contents

    @mock.patch("os.write")
    def test_converts_error(self, mock_write):
        """Should convert OSError to FileCopyError"""
        mock_write.side_effect = OSError
        with pytest.raises(inner.FileCopyError):
            inner.copy_fd_contents(self.target_fd, self.temp_fd)


class TestCopyToTempFile(TestCaseWithFiles):
    """Tests for copy_to_temp_file"""

    def test_copy_to_temp(self):
        """Should copy fd contents to temp file"""
        inner.copy_to_temp_file(
            original_fd=self.target_fd, temp_file=self.temp_filename, uid_gid=(MY_UID, MY_GID)
        )
        with open(self.temp_filename, "rb") as f:
            assert f.read() == self.target_contents
        # Ensure fd wasn't closed
        os.lseek(self.target_fd, 0, os.SEEK_SET)

    @mock.patch("os.close")
    @mock.patch("run0edit_inner.copy_fd_contents")
    @mock.patch("run0edit_inner.open_temp_file")
    def test_calls_open_temp_file(self, mock_open_temp, mock_copy_fd, mock_close):
        """Should copy using fd created with open_temp_file"""
        s = mock.sentinel
        mock_open_temp.return_value = s.temp_fd
        inner.copy_to_temp_file(original_fd=s.orig_fd, temp_file=s.temp_file, uid_gid=s.uid_gid)
        mock_open_temp.assert_called_once_with(s.temp_file, uid_gid=s.uid_gid, flags=mock.ANY)
        mock_copy_fd.assert_called_once_with(src=s.orig_fd, dest=s.temp_fd, bufsize=mock.ANY)
        mock_close.assert_called_once_with(s.temp_fd)


class TestCmpFdContents(unittest.TestCase):
    """Tests for cmp_fd_contents"""

    SHORT_TEXT = b"short string"
    LOREM_IPSUM = b"Lorem ipsum dolor sit amet - "
    LONG_TEXT1 = LOREM_IPSUM * 1000 + b"a" + LOREM_IPSUM * 100
    LONG_TEXT2 = LOREM_IPSUM * 1000 + b"b" + LOREM_IPSUM * 100

    def setUp(self):
        """Set up test files"""
        self.directory = new_test_dir()
        self.file1 = Path(new_test_file(directory=self.directory))
        self.file2 = Path(new_test_file(directory=self.directory))
        read_flags = os.O_CLOEXEC | os.O_NOFOLLOW | os.O_RDONLY
        self.fd1 = os.open(self.file1, read_flags)
        self.fd2 = os.open(self.file2, read_flags)

    def tearDown(self):
        """Clean up test files"""
        for fd in (self.fd1, self.fd2):
            try:
                os.close(fd)
            except OSError:  # pragma: no cover
                pass
        remove_test_dir(self.directory)

    def test_same_inode(self):
        """Should compare equal if FDs refer to same inode"""
        self.file1.write_bytes(self.SHORT_TEXT)
        assert inner.cmp_fd_contents(self.fd1, os.dup(self.fd1))

    def test_different_size(self):
        """Should compare unequal if files differ in size"""
        self.file1.write_bytes(self.SHORT_TEXT)
        self.file2.write_bytes(self.SHORT_TEXT + b".")
        assert not inner.cmp_fd_contents(self.fd1, self.fd2)

    def test_same_size_different_contents(self):
        """Should compare unequal if files match in size but not contents"""
        self.file1.write_bytes(self.LONG_TEXT1)
        self.file2.write_bytes(self.LONG_TEXT2)
        assert not inner.cmp_fd_contents(self.fd1, self.fd2)

    def test_same_contents(self):
        """Should compare equal if files have same contents"""
        self.file1.write_bytes(self.LONG_TEXT1)
        self.file2.write_bytes(self.LONG_TEXT1)
        assert inner.cmp_fd_contents(self.fd1, self.fd2)

    def test_same_contents_with_fd_offset(self):
        """Should seek to beginning both before comparing and before returning"""
        self.file1.write_bytes(self.LONG_TEXT1)
        self.file2.write_bytes(self.LONG_TEXT2)
        os.lseek(self.fd1, 10, os.SEEK_SET)
        os.lseek(self.fd2, 20, os.SEEK_SET)
        assert not inner.cmp_fd_contents(self.fd1, self.fd2)
        assert os.lseek(self.fd1, 0, os.SEEK_CUR) == 0
        assert os.lseek(self.fd2, 0, os.SEEK_CUR) == 0


@mock.patch("run0edit_inner.cmp_fd_contents")
class TestNeedsCopyFromTmp(TestCaseWithFiles):
    """Tests for needs_copy_from_tmp"""

    def test_create_empty_file(self, mock_cmp):
        """Should not need to create empty file"""
        with open(self.temp_filename, "wb"):
            pass
        assert not inner.needs_copy_from_temp(self.temp_fd, self.target_dir_fd, create=True)
        mock_cmp.assert_not_called()

    def test_create_non_empty_file(self, mock_cmp):
        """Should need to create non-empty file"""
        with open(self.temp_filename, "wb") as f:
            f.write(b"non-empty")
        assert inner.needs_copy_from_temp(self.temp_fd, self.target_dir_fd, create=True)
        mock_cmp.assert_not_called()

    def test_cmp_same(self, mock_cmp):
        """Should not need to copy from identical file"""
        mock_cmp.return_value = True
        s = mock.sentinel
        assert not inner.needs_copy_from_temp(s.src_fd, s.dest_fd, create=False)
        mock_cmp.assert_called_once_with(s.src_fd, s.dest_fd, bufsize=mock.ANY)

    def test_cmp_differ(self, mock_cmp):
        """Should need to copy from different file"""
        mock_cmp.return_value = False
        s = mock.sentinel
        assert inner.needs_copy_from_temp(s.src_fd, s.dest_fd, create=False)
        mock_cmp.assert_called_once_with(s.src_fd, s.dest_fd, bufsize=mock.ANY)


@mock.patch("run0edit_inner.needs_copy_from_temp")
@mock.patch("run0edit_inner.FS_IMMUTABLE_FL", MOCK_IMMUTABLE_FL)
class TestCopyFromTempfile(TestCaseWithFiles):
    """Tests for copy_from_temp_file"""

    @mock.patch("run0edit_inner.set_immutable_flag")
    @mock.patch("run0edit_inner.copy_fd_contents")
    def test_no_copy_needed(self, mock_copy_fd, mock_set_immut, mock_needs_copy):
        """Should not copy if copy not needed"""
        mock_needs_copy.return_value = False
        assert not inner.copy_from_temp_file(
            self.temp_filename,
            self.target_fd,
            uid_gid=(MY_UID, MY_GID),
            create_filename=None,
            dest_immutable=False,
        )
        mock_needs_copy.assert_called_once_with(
            mock.ANY, self.target_fd, create=False, bufsize=mock.ANY
        )
        mock_copy_fd.assert_not_called()
        mock_set_immut.assert_not_called()
        assert Path(self.target_filename).read_bytes() == self.target_contents

    @mock.patch("run0edit_inner.set_immutable_flag")
    def test_copy_existing_mutable(self, mock_set_immut, mock_needs_copy):
        """Should copy to existing non-immutable file"""
        mock_needs_copy.return_value = True
        assert inner.copy_from_temp_file(
            self.temp_filename,
            self.target_fd,
            uid_gid=(MY_UID, MY_GID),
            create_filename=None,
            dest_immutable=False,
        )
        mock_needs_copy.assert_called_once_with(
            mock.ANY, self.target_fd, create=False, bufsize=mock.ANY
        )
        mock_set_immut.assert_not_called()
        assert Path(self.target_filename).read_bytes() == self.temp_contents

    def test_fail_copy_existing_missing(self, mock_needs_copy):
        """Should fail to copy to nonexistent file that should exist"""
        mock_needs_copy.return_value = True
        with pytest.raises(inner.FileCopyError):
            inner.copy_from_temp_file(
                self.new_filename,
                self.target_fd,
                uid_gid=(MY_UID, MY_GID),
                create_filename=None,
                dest_immutable=False,
            )
        assert not os.path.exists(self.new_filename)

    @mock.patch("run0edit_inner.set_immutable_flag")
    def test_copy_new_mutable(self, mock_set_immut, mock_needs_copy):
        """Should copy to new non-immutable file"""
        mock_needs_copy.return_value = True
        assert inner.copy_from_temp_file(
            self.temp_filename,
            self.target_dir_fd,
            uid_gid=(MY_UID, MY_GID),
            create_filename=os.path.basename(self.new_filename),
            dest_immutable=False,
        )
        mock_needs_copy.assert_called_once_with(
            mock.ANY, self.target_dir_fd, create=True, bufsize=mock.ANY
        )
        mock_set_immut.assert_not_called()
        assert Path(self.new_filename).read_bytes() == self.temp_contents

    @mock.patch("run0edit_inner.copy_fd_contents")
    def test_fail_copy_new_already_exists(self, mock_copy_fd, mock_needs_copy):
        """Should fail to copy to new file if it already exists"""
        mock_needs_copy.return_value = True
        with pytest.raises(FileExistsError):
            inner.copy_from_temp_file(
                self.temp_filename,
                self.target_dir_fd,
                uid_gid=(MY_UID, MY_GID),
                create_filename=os.path.basename(self.target_filename),
                dest_immutable=False,
            )
        mock_copy_fd.assert_not_called()
        assert Path(self.target_filename).read_bytes() == self.target_contents

    @mock.patch("run0edit_inner.set_immutable_flag")
    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_copy_existing_immutable(self, mock_stdout, mock_set_immut, mock_needs_copy):
        """Should copy to existing immutable file and set immutable attribute"""
        mock_needs_copy.return_value = True
        assert inner.copy_from_temp_file(
            self.temp_filename,
            self.target_fd,
            uid_gid=(MY_UID, MY_GID),
            create_filename=None,
            dest_immutable=True,
        )
        assert Path(self.target_filename).read_bytes() == self.temp_contents
        assert mock_stdout.getvalue() == "Immutable attribute reapplied.\n"
        assert mock_set_immut.call_count == 2
        mock_set_immut.assert_has_calls(
            (mock.call(self.target_fd, False), mock.call(self.target_fd, True))
        )

    @mock.patch("run0edit_inner.set_immutable_flag")
    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_copy_new_immutable(self, mock_stdout, mock_set_immut, mock_needs_copy):
        """Should copy to new immutable file and set immutable attributes"""
        mock_needs_copy.return_value = True
        assert inner.copy_from_temp_file(
            self.temp_filename,
            self.target_dir_fd,
            uid_gid=(MY_UID, MY_GID),
            create_filename=os.path.basename(self.new_filename),
            dest_immutable=True,
        )
        assert Path(self.new_filename).read_bytes() == self.temp_contents
        assert mock_stdout.getvalue() == "Immutable attribute reapplied.\n"
        assert mock_set_immut.call_count == 3
        mock_set_immut.assert_has_calls(
            (
                mock.call(self.target_dir_fd, False),
                mock.call(self.target_dir_fd, True),
                mock.call(mock.ANY, True),
            )
        )

    @mock.patch("hashlib.file_digest")
    @mock.patch("run0edit_inner.set_immutable_flag")
    @mock.patch("sys.stdout", new_callable=io.StringIO)
    def test_copy_immutable_checksum_mismatch(
        self, mock_stdout, mock_set_immut, mock_file_digest, mock_needs_copy
    ):
        """Should raise exception after copy to immutable file if checksums don't match"""
        mock_needs_copy.return_value = True
        mock_file_digest.return_value = hashlib.blake2b(b"bad data")
        with pytest.raises(inner.FileContentsMismatchError):
            inner.copy_from_temp_file(
                self.temp_filename,
                self.target_fd,
                uid_gid=(MY_UID, MY_GID),
                create_filename=None,
                dest_immutable=True,
            )
        assert Path(self.target_filename).read_bytes() == self.temp_contents
        assert mock_stdout.getvalue() == "Immutable attribute reapplied.\n"
        assert mock_set_immut.call_count == 2
        mock_set_immut.assert_has_calls(
            (mock.call(self.target_fd, False), mock.call(self.target_fd, True))
        )
        mock_file_digest.assert_called_once_with(mock.ANY, "blake2b")


@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_inner.copy_from_temp_file")
class TestHandleCopyFromTempFile(TestCaseWithFiles):
    """Tests for handle_copy_from_temp_file"""

    def test_check_args(self, mock_copy, mock_stdout):
        """Check copy_from_temp_file is called with expected arguments"""
        mock_copy.return_value = True
        s = mock.sentinel
        inner.handle_copy_from_temp_file(
            temp_file=self.temp_filename,
            original_fd=s.orig_fd,
            original_path=self.target_filename,
            uid_gid=s.uid_gid,
            original_file_exists=s.exists,
            immutable=s.immut,
        )
        mock_copy.assert_called_once_with(
            temp_file=self.temp_filename,
            dest_fd=s.orig_fd,
            uid_gid=s.uid_gid,
            create_filename=mock.ANY,
            dest_immutable=s.immut,
        )
        assert mock_stdout.getvalue() == ""

    def test_file_exists_copy_needed(self, mock_copy, mock_stdout):
        """Case where the file exists and a copy is needed"""
        mock_copy.return_value = True
        inner.handle_copy_from_temp_file(
            temp_file=self.temp_filename,
            original_fd=self.target_fd,
            original_path=self.target_filename,
            uid_gid=(MY_UID, MY_GID),
            original_file_exists=True,
            immutable=False,
        )
        mock_copy.assert_called_once()
        assert mock_copy.call_args.kwargs["create_filename"] is None
        assert mock_stdout.getvalue() == ""

    def test_new_file_copy_needed(self, mock_copy, mock_stdout):
        """Case where the file does not exist and a copy is needed"""
        mock_copy.return_value = True
        inner.handle_copy_from_temp_file(
            temp_file=self.temp_filename,
            original_fd=self.target_fd,
            original_path=self.target_filename,
            uid_gid=(MY_UID, MY_GID),
            original_file_exists=False,
            immutable=False,
        )
        mock_copy.assert_called_once()
        assert mock_copy.call_args.kwargs["create_filename"] == os.path.basename(
            self.target_filename
        )
        assert mock_stdout.getvalue() == ""

    def test_file_exists_no_copy(self, mock_copy, mock_stdout):
        """Case where the file exists and no copy is needed"""
        mock_copy.return_value = False
        inner.handle_copy_from_temp_file(
            temp_file=self.temp_filename,
            original_fd=self.target_fd,
            original_path=self.target_filename,
            uid_gid=(MY_UID, MY_GID),
            original_file_exists=True,
            immutable=False,
        )
        mock_copy.assert_called_once()
        assert mock_copy.call_args.kwargs["create_filename"] is None
        assert mock_stdout.getvalue() == f"run0edit: {self.target_filename} unchanged\n"

    def test_new_file_no_copy(self, mock_copy, mock_stdout):
        """Case where the file does not exist and no copy is needed"""
        mock_copy.return_value = False
        inner.handle_copy_from_temp_file(
            temp_file=self.temp_filename,
            original_fd=self.target_fd,
            original_path=self.target_filename,
            uid_gid=(MY_UID, MY_GID),
            original_file_exists=False,
            immutable=False,
        )
        mock_copy.assert_called_once()
        assert mock_copy.call_args.kwargs["create_filename"] == os.path.basename(
            self.target_filename
        )
        assert mock_stdout.getvalue() == f"run0edit: {self.target_filename} not created\n"

    def test_error_messages(self, mock_copy, mock_stdout):
        """Should print appropriate error messages and re-raise exceptions"""
        errors: dict[type[Exception], str] = {
            inner.ChattrError: "failed to set immutable attribute",
            inner.FileContentsMismatchError: "does not match contents of edited tempfile",
            inner.FileCopyError: "unable to copy contents of temporary file",
        }
        mock_copy.side_effect = iter(errors)
        for exc, message in errors.items():
            with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                with pytest.raises(exc):
                    inner.handle_copy_from_temp_file(
                        temp_file=self.temp_filename,
                        original_fd=self.target_fd,
                        original_path=self.target_filename,
                        uid_gid=(MY_UID, MY_GID),
                        original_file_exists=True,
                        immutable=False,
                    )
                assert message in mock_stderr.getvalue().casefold()
        assert mock_stdout.getvalue() == ""


@mock.patch("run0edit_inner.run_command")
class TestRunEditor(unittest.TestCase):
    """Tests for run_editor"""

    @mock.patch("run0edit_inner.find_command")
    def test_check_args(self, mock_find_cmd, mock_run_cmd):
        """Should pass correct arguments to run_command"""
        user = getpass.getuser()
        editor = mock.sentinel.editor
        path = mock.sentinel.path
        mock_find_cmd.side_effect = lambda cmd: f"/bin/{cmd}"
        inner.run_editor(uid=MY_UID, editor=editor, path=path)
        mock_run_cmd.assert_called_once_with(
            "runuser", "--pty", "-", user, "-c", 'exec "$0" "$1"', editor, path
        )

    def test_error_messages(self, mock_run_cmd):
        """Should print appropriate error messages and raise EditTempFileError"""
        errors = {
            inner.CommandNotFoundError: "failed to call runuser to start editor",
            inner.SubprocessError: "failed to edit temporary file",
        }
        mock_run_cmd.side_effect = iter(errors)
        for message in errors.values():
            with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                with pytest.raises(inner.EditTempFileError):
                    inner.run_editor(uid=MY_UID, editor="butterfly", path="some/path")
                assert message in mock_stderr.getvalue()


@mock.patch("sys.stdout", new_callable=io.StringIO)
@mock.patch("run0edit_inner.run_editor")
class TestRun(TestCaseWithFiles):
    """Tests for run"""

    def edit_temp_file(self, data: bytes) -> None:
        """Helper method to simulate the user editing the temp file"""
        with open(self.temp_filename, "wb") as f:
            f.write(data)

    @mock.patch("os.close", lambda _: None)
    @mock.patch("run0edit_inner.handle_copy_from_temp_file")
    @mock.patch("run0edit_inner.copy_to_temp_file")
    @mock.patch("run0edit_inner.handle_check_readonly")
    @mock.patch("run0edit_inner.get_fd_for_original")
    @mock.patch("os.path.realpath")
    def test_check_args(
        self,
        m_realpath,
        m_get_fd,
        m_check_ro,
        m_copy_to_temp,
        m_copy_from_temp,
        m_run_editor,
        m_stdout,
    ):
        """Should pass correct arguments to functions"""
        s = mock.sentinel
        m_realpath.return_value = s.realpath
        m_get_fd.return_value = (s.fd_orig, True)
        m_check_ro.return_value = s.immutable
        inner.run(s.filename, s.temp_filename, s.editor, uid_gid=(s.uid, s.gid))
        m_realpath.assert_called_once_with(s.filename)
        m_get_fd.assert_called_once_with(s.realpath)
        m_check_ro.assert_called_once_with(s.fd_orig, s.realpath, prompt_immutable=True)
        m_copy_to_temp.assert_called_once_with(
            original_fd=s.fd_orig, temp_file=s.temp_filename, uid_gid=(s.uid, s.gid)
        )
        m_run_editor.assert_called_once_with(uid=s.uid, editor=s.editor, path=s.temp_filename)
        m_copy_from_temp.assert_called_once_with(
            temp_file=s.temp_filename,
            original_fd=s.fd_orig,
            original_path=s.realpath,
            uid_gid=(s.uid, s.gid),
            original_file_exists=True,
            immutable=s.immutable,
        )
        assert m_stdout.getvalue() == ""

    @mock.patch("run0edit_inner.get_fd_for_original")
    def test_get_fd_error_messages(self, mock_get_fd, mock_run_editor, mock_stdout):
        """
        Should print expected error messages and re-raise exceptions for get_fd_for_original
        """
        errors: dict[type[inner.Run0editError], str] = {
            inner.NoDirectoryError: "invalid argument: directory does not exist",
            inner.NotRegularFileError: "invalid argument: not a regular file",
        }
        mock_get_fd.side_effect = iter(errors)
        for exc, message in errors.items():
            with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                with pytest.raises(exc):
                    inner.run(
                        self.target_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID)
                    )
                assert message in mock_stderr.getvalue().casefold()
        mock_get_fd.assert_called()
        mock_run_editor.assert_not_called()
        assert mock_stdout.getvalue() == ""

    @mock.patch("run0edit_inner.handle_check_readonly")
    def test_check_ro_error_messages(self, mock_check_ro, mock_run_editor, mock_stdout):
        """
        Should print expected error messages and re-raise exceptions for handle_check_readonly
        """
        errors: dict[type[inner.Run0editError], str] = {
            inner.ReadOnlyFilesystemError: "read-only filesystem",
            inner.ReadOnlyOtherError: "is read-only",
        }
        mock_check_ro.side_effect = iter(errors)
        for exc, message in errors.items():
            with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
                with pytest.raises(exc):
                    inner.run(
                        self.target_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID)
                    )
                stderr = mock_stderr.getvalue().replace("-\n", "-").replace("\n", " ").casefold()
                assert message in stderr
        mock_check_ro.assert_called()
        mock_run_editor.assert_not_called()
        assert mock_stdout.getvalue() == ""

    @mock.patch("run0edit_inner.handle_check_readonly")
    def test_declined_immutable(self, mock_check_ro, mock_run_editor, mock_stdout):
        """Should return early with expected message if user declines to edit immutable file"""
        mock_check_ro.side_effect = inner.ReadOnlyImmutableError
        inner.run(self.target_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID))
        mock_check_ro.assert_called()
        mock_run_editor.assert_not_called()
        assert (
            mock_stdout.getvalue()
            == "run0edit: user declined to remove immutable attribute; exiting.\n"
        )

    @mock.patch("run0edit_inner.copy_to_temp_file")
    def test_copy_to_temp_fail(self, mock_copy_to_temp, mock_run_editor, mock_stdout):
        """Should print message and raise FileCopyError if copy to temp fails"""
        mock_copy_to_temp.side_effect = inner.FileCopyError
        with mock.patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            with pytest.raises(inner.FileCopyError):
                inner.run(self.target_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID))
            stderr = mock_stderr.getvalue().replace("-\n", "-").replace("\n", " ")
        mock_copy_to_temp.assert_called_once()
        mock_run_editor.assert_not_called()
        assert re.search(r" failed to copy .* to temporary file ", stderr)
        assert mock_stdout.getvalue() == ""

    @mock.patch("run0edit_inner.copy_to_temp_file")
    def test_new_file_no_copy(self, mock_copy_to_temp, mock_run_editor, mock_stdout):
        """Should not try copying nonexistent file to temp file"""
        mock_run_editor.side_effect = Exception("mock run editor")
        with pytest.raises(Exception, match="mock run editor"):
            inner.run(self.new_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID))
        mock_copy_to_temp.assert_not_called()
        mock_run_editor.assert_called_once()
        assert mock_stdout.getvalue() == ""

    def test_edit_file(self, mock_run_editor, mock_stdout):
        """Should copy edited tempfile contents to target file"""
        text = b"Lorum ipsum dolor sit amet"
        mock_run_editor.side_effect = lambda **_: self.edit_temp_file(text)
        inner.run(self.target_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID))
        with open(self.target_filename, "rb") as f:
            assert f.read() == text
        mock_run_editor.assert_called_once()
        assert mock_stdout.getvalue() == ""

    def test_edit_unchanged(self, mock_run_editor, mock_stdout):
        """Should report tempfile contents unchanged"""
        inner.run(self.target_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID))
        with open(self.target_filename, "rb") as f:
            assert f.read() == self.target_contents
        mock_run_editor.assert_called_once()
        assert "unchanged" in mock_stdout.getvalue()

    def test_create_file(self, mock_run_editor, mock_stdout):
        """Should copy edited tempfile contents to new file"""
        text = b"Lorum ipsum dolor sit amet"
        mock_run_editor.side_effect = lambda **_: self.edit_temp_file(text)
        inner.run(self.new_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID))
        with open(self.new_filename, "rb") as f:
            assert f.read() == text
        assert mock_stdout.getvalue() == ""

    def test_create_empty(self, mock_run_editor, mock_stdout):
        """Should not create empty new file"""
        with open(self.temp_filename, "wb"):
            pass
        inner.run(self.new_filename, self.temp_filename, "ed", uid_gid=(MY_UID, MY_GID))
        assert not os.path.exists(self.new_filename)
        mock_run_editor.assert_called_once()
        assert "not created" in mock_stdout.getvalue()


@mock.patch("sys.stderr", new_callable=io.StringIO)
class TestParseArgs(unittest.TestCase):
    """Tests for parse_args"""

    ARGS = (mock.sentinel.a0, mock.sentinel.a1, mock.sentinel.a2)

    def test_parse_args(self, mock_stderr):
        """Should return three provided arguments plus None"""
        assert inner.parse_args(self.ARGS) == self.ARGS
        assert mock_stderr.getvalue() == ""

    def test_too_few_args(self, mock_stderr):
        """Should print expected message and raise exception if too few arguments"""
        with pytest.raises(inner.InvalidArgumentsError):
            inner.parse_args(self.ARGS[:2])
        assert mock_stderr.getvalue() == "run0edit_inner.py: Error: too few arguments\n"

    def test_too_many_args(self, mock_stderr):
        """Should print expected message and raise exception if too many arguments"""
        with pytest.raises(inner.InvalidArgumentsError):
            inner.parse_args([*self.ARGS, "???"])
        assert mock_stderr.getvalue() == "run0edit_inner.py: Error: too many arguments\n"


class TestRemoveTempFile(TestCaseWithFiles):
    """Tests for remove_temp_file"""

    def test_removes_temp_file_and_dir(self):
        """Should remove test file and test directory."""
        assert os.path.isdir(self.temp_dir)
        assert os.path.isfile(self.temp_filename)
        inner.remove_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID), only_if_empty=False)
        assert not os.path.exists(self.temp_dir)
        assert not os.path.exists(self.temp_filename)

    def test_removes_empty_file(self):
        """Should remove empty temp file if only_if_empty is set"""
        assert os.path.isdir(self.temp_dir)
        assert os.path.isfile(self.temp_filename)
        with open(self.temp_filename, "wb"):
            pass
        inner.remove_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID), only_if_empty=True)
        assert not os.path.exists(self.temp_dir)
        assert not os.path.exists(self.temp_filename)

    def test_preserves_nonempty_file(self):
        """Should not remove non-empty temp file if only_if_empty is set"""
        assert os.path.isdir(self.temp_dir)
        assert os.path.isfile(self.temp_filename)
        inner.remove_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID), only_if_empty=True)
        assert os.path.exists(self.temp_dir)
        assert os.path.exists(self.temp_filename)

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_preserves_directory_if_unexpected_file(self, mock_stderr):
        """Should remove file but not directory if unexpected extra file is present"""
        unexpected_file = Path(self.temp_dir) / "unexpected"
        unexpected_file.touch(mode=0o600)
        assert os.path.isdir(self.temp_dir)
        assert os.path.isfile(self.temp_filename)
        assert os.path.isfile(unexpected_file)
        inner.remove_temp_file(self.temp_filename, uid_gid=(MY_UID, MY_GID))
        assert os.path.exists(self.temp_dir)
        assert not os.path.exists(self.temp_filename)
        assert os.path.isfile(unexpected_file)
        assert "run0edit: Warning: failed to remove temporary directory" in mock_stderr.getvalue()


@mock.patch("run0edit_inner.remove_temp_file")
@mock.patch("run0edit_inner.run")
@mock.patch("os.environ", new={"SUDO_UID": MY_UID, "SUDO_GID": MY_GID})
class TestMain(unittest.TestCase):
    """Tests for main"""

    ARGS = (mock.sentinel.a0, mock.sentinel.a1, mock.sentinel.a2)

    @mock.patch("run0edit_inner.parse_args")
    def test_parses_args(self, mock_parse_args, mock_run, mock_rm_temp):
        """Should parse arguments using parse_args"""
        mock_parse_args.return_value = self.ARGS
        inner.main(mock.sentinel.main_args)
        mock_parse_args.assert_called_once_with(mock.sentinel.main_args)
        mock_run.assert_called_once_with(
            *self.ARGS, uid_gid=(MY_UID, MY_GID), prompt_immutable=True
        )
        mock_rm_temp.assert_called_once_with(self.ARGS[1], uid_gid=(MY_UID, MY_GID))

    @mock.patch("run0edit_inner.parse_args")
    def test_invalid_args(self, mock_parse_args, mock_run, mock_rm_temp):
        """Should return 2 if parse_args raises InvalidArgumentsError"""
        mock_parse_args.side_effect = inner.InvalidArgumentsError
        assert inner.main(mock.sentinel.main_args) == 2
        mock_run.assert_not_called()
        mock_rm_temp.assert_not_called()

    def test_normal_run(self, mock_run, mock_rm_temp):
        """Should pass correct args to run and return 0"""
        assert inner.main(self.ARGS) == 0
        mock_run.assert_called_once_with(
            *self.ARGS, uid_gid=(MY_UID, MY_GID), prompt_immutable=True
        )
        mock_rm_temp.assert_called_once_with(self.ARGS[1], uid_gid=(MY_UID, MY_GID))

    def test_failed_run(self, mock_run, mock_rm_temp):
        """Should pass correct args to run and return 1"""
        mock_run.side_effect = inner.Run0editError
        assert inner.main(self.ARGS) == 1
        mock_run.assert_called_once_with(
            *self.ARGS, uid_gid=(MY_UID, MY_GID), prompt_immutable=True
        )
        mock_rm_temp.assert_called_once_with(
            self.ARGS[1], uid_gid=(MY_UID, MY_GID), only_if_empty=True
        )

    @mock.patch.dict("os.environ", {"RUN0EDIT_DEBUG": "1"})
    def test_failed_run_debug(self, mock_run, mock_rm_temp):
        """Should pass correct args to run and raise exception"""
        mock_run.side_effect = inner.Run0editError
        with pytest.raises(inner.Run0editError):
            inner.main(self.ARGS)
        mock_run.assert_called_once_with(
            *self.ARGS, uid_gid=(MY_UID, MY_GID), prompt_immutable=True
        )
        mock_rm_temp.assert_called_once_with(
            self.ARGS[1], uid_gid=(MY_UID, MY_GID), only_if_empty=True
        )
