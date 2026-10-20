#!/usr/bin/env python3

# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Inner script for run0edit. Not meant to be run directly.

Please report issues at: https://github.com/HastD/run0edit/issues
"""

import ctypes
import enum
import errno
import fcntl
import hashlib
import os
import pwd
import resource
import shutil
import stat
import struct
import subprocess  # nosec
import sys
import textwrap
from collections.abc import Sequence
from typing import Final, assert_never


class Run0editError(Exception):
    """Base class for run0edit errors."""


class CommandNotFoundError(Run0editError):
    """An external command was not found."""


class NotRegularFileError(Run0editError):
    """Target file is not a regular file."""


class NoDirectoryError(Run0editError):
    """Directory does not exist."""


class ReadOnlyFilesystemError(Run0editError):
    """File is on a read-only filesystem."""


class ReadOnlyImmutableError(Run0editError):
    """File is read-only because of the immutable attribute."""


class ReadOnlyOtherError(Run0editError):
    """File is read-only for another reason."""


class EditTempFileError(Run0editError):
    """Failed to edit the temp file."""


class FileCopyError(Run0editError):
    """Failed to copy to the target file."""


class SubprocessError(Run0editError):
    """An external command failed."""


class ChattrError(Run0editError):
    """Changing immutable attribute failed."""


class FileContentsMismatchError(Run0editError):
    """File contents are not what they should be."""


def _ioc_macro(direction: int, ty: int, nr: int, size: int) -> int:
    """
    Python implementation of the _IOC macro for generating ioctl numbers from
    include/uapi/asm-generic/ioctl.h in the Linux kernel.
    """
    _IOC_NRBITS = 8
    _IOC_TYPEBITS = 8
    _IOC_SIZEBITS = 14
    _IOC_DIRBITS = 2
    _IOC_NRMASK = (1 << _IOC_NRBITS) - 1
    _IOC_TYPEMASK = (1 << _IOC_TYPEBITS) - 1
    _IOC_SIZEMASK = (1 << _IOC_SIZEBITS) - 1
    _IOC_DIRMASK = (1 << _IOC_DIRBITS) - 1
    _IOC_NRSHIFT = 0
    _IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
    _IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
    _IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
    return (
        (direction << _IOC_DIRSHIFT)
        | (ty << _IOC_TYPESHIFT)
        | (nr << _IOC_NRSHIFT)
        | (size << _IOC_SIZESHIFT)
    )


def _ior_macro(ty: int, nr: int, size: int) -> int:
    """Implementation of _IOR macro from Linux kernel."""
    return _ioc_macro(2, ty, nr, size)


def _iow_macro(ty: int, nr: int, size: int) -> int:
    """Implementation of _IOW macro from Linux kernel."""
    return _ioc_macro(1, ty, nr, size)


# Definitions from Linux kernel in include/uapi/linux/fs.h
FS_IOC_GETFLAGS: Final[int] = _ior_macro(ord("f"), 1, ctypes.sizeof(ctypes.c_long))
FS_IOC_SETFLAGS: Final[int] = _iow_macro(ord("f"), 2, ctypes.sizeof(ctypes.c_long))
FS_IMMUTABLE_FL: Final[int] = 0x00000010


def get_inode_flags(fd: int) -> int:
    """Get inode flags of file descriptor."""
    flags_packed = bytearray(struct.pack("i", 0))
    fcntl.ioctl(fd, FS_IOC_GETFLAGS, flags_packed)
    return struct.unpack("i", flags_packed)[0]


def is_immutable(fd: int) -> bool:
    """Determine if the file descriptor has the immutable attribute."""
    try:
        return bool(get_inode_flags(fd) & FS_IMMUTABLE_FL)
    except OSError:
        return False


def set_immutable_flag(fd: int, immutable: bool) -> None:
    """Set or unset the immutable flag on the file descriptor."""
    try:
        flags = get_inode_flags(fd)
        already_immutable = bool(flags & FS_IMMUTABLE_FL)
        if immutable == already_immutable:
            return
        flags ^= FS_IMMUTABLE_FL
        flags_packed = struct.pack("i", flags)
        fcntl.ioctl(fd, FS_IOC_SETFLAGS, flags_packed)
    except OSError as e:
        raise ChattrError from e


def prompt_remove_immutable(path: str, is_dir: bool) -> bool:
    """Ask the user whether to temporarily remove the immutable attribute."""
    print(f"{path} has the immutable attribute.")
    if is_dir:
        prompt = "Temporarily remove attribute to create a file in the directory? [y/N] "
    else:
        prompt = "Temporarily remove the attribute to edit the file? [y/N] "
    response = input(prompt).casefold()
    return response in ("y", "yes")


def print_err(message: str, *, wrap: bool = True) -> None:
    """Print error message to stderr with text wrapping."""
    text = "run0edit: " + textwrap.dedent(message.strip("\n"))
    if wrap:
        text = textwrap.fill(text, width=80)
    print(text, file=sys.stderr)


def readonly_filesystem(file: str | int) -> bool | None:
    """Determine if the file is on a read-only filesystem."""
    try:
        return bool(os.statvfs(file).f_flag & os.ST_RDONLY)
    except OSError:
        return None


def find_command(command: str) -> str:
    """Search for command using a default path."""
    cmd_path = shutil.which(command, path="/usr/bin:/bin:/usr/sbin:/sbin")
    if cmd_path is None:
        raise CommandNotFoundError(command)
    return cmd_path


def run_command(cmd: str, *args: str, capture_output: bool = False) -> str | None:
    """Run command as subprocess."""
    run_args = [find_command(cmd), *args]
    try:
        result = subprocess.run(
            run_args, check=True, shell=False, capture_output=capture_output, text=capture_output
        )  # nosec
    except subprocess.CalledProcessError as e:
        raise SubprocessError from e
    if capture_output:
        return str(result.stdout)
    return None


def get_dir_fd(path: str, *, dir_fd: int | None = None) -> int:
    """Open dir_fd for directory, optionally with a parent dir_fd."""
    return os.open(path, os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_RDONLY, dir_fd=dir_fd)


def get_fd_for_original(path: str) -> tuple[int, bool]:
    """
    Get either a read-only file descriptor for a file at the given path, or a
    file descriptor for the parent directory if the file doesn't exist. Returns
    the file descriptor and a boolean indicating whether the file exists.

    Raises an exception if the path points to a non-regular file or if the
    parent of the path is not a directory.
    """
    directory, filename = os.path.split(path)
    try:
        dir_fd = get_dir_fd(directory)
    except FileNotFoundError as e:
        raise NoDirectoryError(f"{directory} does not exist") from e
    except NotADirectoryError as e:
        raise NoDirectoryError(f"{directory} is not a directory") from e

    try:
        file_fd = os.open(
            filename,
            flags=os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_RDONLY,
            dir_fd=dir_fd,
        )
    except FileNotFoundError:
        return dir_fd, False
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise NotRegularFileError(f"{path} is not a regular file") from e
        raise

    if not stat.S_ISREG(os.fstat(file_fd).st_mode):
        raise NotRegularFileError(f"{path} is not a regular file")

    return file_fd, True


class FileStatus(enum.Enum):
    """Whether a file is writable, and if not, reason why it's read-only"""

    READ_WRITE = enum.auto()
    IMMUTABLE = enum.auto()
    READ_ONLY_FS = enum.auto()
    READ_ONLY_OTHER = enum.auto()


def check_readonly(fd: int) -> FileStatus:
    """
    Return whether the file pointed to by the file descriptor is readable and
    writable, and if not, whether it's immutable, on a read-only filesystem, or
    read-only for other reasons.
    """
    try:
        rw_fd = os.open(f"/proc/self/fd/{fd}", flags=os.O_CLOEXEC | os.O_RDWR)
    except IsADirectoryError:
        if os.access(".", os.R_OK | os.W_OK, dir_fd=fd, follow_symlinks=False):
            return FileStatus.READ_WRITE
    except OSError:
        pass
    else:
        os.close(rw_fd)
        return FileStatus.READ_WRITE
    if readonly_filesystem(fd):
        return FileStatus.READ_ONLY_FS
    if is_immutable(fd):
        return FileStatus.IMMUTABLE
    return FileStatus.READ_ONLY_OTHER


def handle_check_readonly(fd: int, path: str, *, prompt_immutable: bool = True) -> bool:
    """
    Handle result of check_readonly. Returns if the file descriptor points to
    an immutable file or directory. Raises an exception if the user declines to
    edit an immutable file, or if the file is read-only for other reasons.
    """
    match check_readonly(fd):
        case FileStatus.READ_WRITE:
            return False
        case FileStatus.IMMUTABLE:
            is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
            if prompt_immutable and not prompt_remove_immutable(path, is_dir):
                raise ReadOnlyImmutableError
            return True
        case FileStatus.READ_ONLY_FS:
            raise ReadOnlyFilesystemError
        case FileStatus.READ_ONLY_OTHER:
            raise ReadOnlyOtherError
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def open_temp_file(path: str, *, uid_gid: tuple[int, int], flags: int = 0) -> int:
    """
    Open the temporary file as the specified UID/GID, and return a file
    descriptor for the opened file. Verifies that the temporary file is owned
    by the user, is not a symlink, and does not have other hardlinks.
    """
    uid, gid = uid_gid
    try:
        os.setegid(gid)
        os.seteuid(uid)
        fd = os.open(path, flags | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        st = os.fstat(fd)
    except OSError as e:
        raise FileCopyError from e
    finally:
        os.seteuid(os.getuid())
        os.setegid(os.getgid())
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise FileCopyError(f"{path} is not a regular file")
    if st.st_uid != uid:
        os.close(fd)
        raise FileCopyError(f"{path} is not owned by UID {uid}")
    if st.st_nlink != 1:
        os.close(fd)
        raise FileCopyError(f"{path} is not a singly-linked file")
    return fd


def reopen_fd(fd: int, flags: int, *, mode: int = 0o644) -> int:
    """Use /proc/self/fd to reopen a file descriptor with different flags."""
    new_fd = os.open(f"/proc/self/fd/{fd}", flags=flags, mode=mode)
    dup_fd = os.dup2(new_fd, fd, inheritable=False)
    os.close(new_fd)
    return dup_fd


def copy_fd_contents(
    src: int, dest: int, *, bufsize: int = 4096, checksum: bool = False
) -> bytes | None:
    """
    Copy file contents from one file descriptor to another. Does not close the
    file descriptors. Optionally computes a checksum of the copied contents.
    """
    if checksum:
        b2hash = hashlib.blake2b()
    try:
        with os.fdopen(dest, "wb", closefd=False) as f_dest:
            while True:
                buffer = os.read(src, bufsize)
                if not buffer:
                    break
                f_dest.write(buffer)
                if checksum:
                    b2hash.update(buffer)
    except OSError as e:
        raise FileCopyError from e
    return b2hash.digest() if checksum else None


def copy_to_temp_file(*, original_fd: int, temp_file: str, uid_gid: tuple[int, int]) -> None:
    """
    Copy contents of original file (given by file descriptor) to temp file.
    Does not copy metadata. Does not close the file descriptor of the original
    file.
    """
    temp_fd = open_temp_file(temp_file, uid_gid=uid_gid, flags=os.O_WRONLY | os.O_TRUNC)
    copy_fd_contents(src=original_fd, dest=temp_fd, bufsize=resource.getpagesize())
    os.close(temp_fd)


def cmp_fd_contents(fd1: int, fd2: int, *, bufsize: int = 4096) -> bool:
    """
    Determine if contents of two file descriptors match. Does not close the
    file descriptors.
    """
    st1 = os.fstat(fd1)
    st2 = os.fstat(fd2)
    if st1.st_ino == st2.st_ino:
        return True
    if st1.st_size != st2.st_size:
        return False
    try:
        with (
            os.fdopen(fd1, "rb", closefd=False) as f1,
            os.fdopen(fd2, "rb", closefd=False) as f2,
        ):
            f1.seek(0, os.SEEK_SET)
            f2.seek(0, os.SEEK_SET)
            while True:
                buf1 = f1.read(bufsize)
                buf2 = f2.read(bufsize)
                if buf1 != buf2:
                    return False
                if not buf1:
                    return True
    finally:
        os.lseek(fd1, 0, os.SEEK_SET)
        os.lseek(fd2, 0, os.SEEK_SET)


def needs_copy_from_temp(src_fd: int, dest_fd: int, *, create: bool, bufsize: int = 4096) -> bool:
    """Return whether copying from the temporary file is necessary."""
    return (
        os.fstat(src_fd).st_size > 0
        if create
        else not cmp_fd_contents(src_fd, dest_fd, bufsize=bufsize)
    )


def copy_from_temp_file(
    temp_file: str,
    dest_fd: int,
    *,
    uid_gid: tuple[int, int],
    create_filename: str | None = None,
    dest_immutable: bool = False,
) -> bool:
    """
    Copy contents of temp file to original file (given by file descriptor).
    Does not copy metadata. If `create_filename` is not None, then `dest_fd`
    points to the directory the file should be created in.

    Arguments:
    * `uid` and `gid` are the UID and GID used to open the temporary file.
    * `create`: whether dest *must* be newly created or *must not* be
      created.
    * `dest_immutable`: whether dest requires toggling immutable attribute.

    Returns boolean indicating whether copy was necessary: false if destination
    file was to be created and temp file was empty, or if destination file
    existed and had same contents as temp file.
    """
    temp_fd = open_temp_file(temp_file, uid_gid=uid_gid, flags=os.O_RDONLY)
    bufsize = resource.getpagesize()

    if not needs_copy_from_temp(
        temp_fd, dest_fd, create=create_filename is not None, bufsize=bufsize
    ):
        return False

    modified_fds = [dest_fd]
    if dest_immutable:
        set_immutable_flag(dest_fd, False)

    try:
        dest_flags = os.O_CLOEXEC | os.O_TRUNC | os.O_WRONLY
        if create_filename is None:
            dest_file_fd = reopen_fd(dest_fd, flags=dest_flags)
        else:
            dest_flags |= os.O_CREAT | os.O_EXCL
            dest_file_fd = os.open(create_filename, flags=dest_flags, dir_fd=dest_fd, mode=0o644)
            modified_fds.append(dest_file_fd)
        checksum = copy_fd_contents(
            src=temp_fd, dest=dest_file_fd, bufsize=bufsize, checksum=dest_immutable
        )
    finally:
        if dest_immutable:
            for fd in modified_fds:
                set_immutable_flag(fd, True)
            print("Immutable attribute reapplied.")

    if dest_immutable:
        dest_file_fd = reopen_fd(dest_file_fd, flags=os.O_CLOEXEC | os.O_RDONLY)
        with os.fdopen(dest_file_fd, "rb", closefd=False) as f_dest:
            dest_checksum = hashlib.file_digest(f_dest, "blake2b").digest()
        if checksum != dest_checksum:
            raise FileContentsMismatchError

    os.close(temp_fd)
    return True


def handle_copy_from_temp_file(
    temp_file: str,
    original_fd: int,
    original_path: str,
    *,
    uid_gid: tuple[int, int],
    original_file_exists: bool,
    immutable: bool,
) -> None:
    """
    If the target file exists and has been modified in the temp file, or
    if this is a new file that is non-empty, copy temp file to target.
    Handle errors or manipulate immutable attribute if needed.
    """
    create_filename = None if original_file_exists else os.path.basename(original_path)
    try:
        copy_needed = copy_from_temp_file(
            temp_file=temp_file,
            dest_fd=original_fd,
            uid_gid=uid_gid,
            create_filename=create_filename,
            dest_immutable=immutable,
        )
    except ChattrError:
        chattr_path = original_path if original_file_exists else os.path.dirname(original_path)
        print_err(
            f"""
            WARNING: Failed to set immutable attribute on {chattr_path}.
            The immutable attribute may have been removed!
            """
        )
        raise
    except FileContentsMismatchError:
        print_err(
            f"""
            WARNING: contents of {original_path} does not match contents of edited tempfile.
            File contents may be corrupted!
            """
        )
        raise
    except (FileCopyError, OSError) as e:
        print_err(f"unable to copy contents of temporary file at {temp_file} to {original_path}")
        raise FileCopyError from e
    if not copy_needed:
        print(f"run0edit: {original_path} {'unchanged' if original_file_exists else 'not created'}")


def run_editor(*, uid: int, editor: str, path: str) -> None:
    """Run the editor as the given UID to edit the file at the given path."""
    user = pwd.getpwuid(uid).pw_name
    try:
        # We use a login shell here to ensure the unprivileged editor has the environment
        # associated with a fresh shell session for that user.
        run_command("runuser", "--pty", "-", user, "-c", 'exec "$0" "$1"', editor, path)
    except CommandNotFoundError as e:
        print_err("failed to call runuser to start editor")
        raise EditTempFileError from e
    except SubprocessError as e:
        print_err(f"failed to edit temporary file at {path}")
        raise EditTempFileError from e


def run(
    original_file: str,
    temp_file: str,
    editor: str,
    uid_gid: tuple[int, int],
    *,
    prompt_immutable: bool = True,
) -> None:
    """
    Copy file to temp file, run editor, and copy temp file back to target file.
    Raises Run0editError if a step fails.
    """
    original_file = os.path.realpath(original_file)
    try:
        original_fd, original_file_exists = get_fd_for_original(original_file)
    except NoDirectoryError:
        print_err("invalid argument: directory does not exist")
        raise
    except NotRegularFileError:
        print_err("invalid argument: not a regular file")
        raise

    try:
        base_path = original_file if original_file_exists else os.path.dirname(original_file)
        immutable = handle_check_readonly(original_fd, base_path, prompt_immutable=prompt_immutable)
    except ReadOnlyImmutableError:
        print("run0edit: user declined to remove immutable attribute; exiting.")
        return
    except ReadOnlyFilesystemError:
        print_err(f"{base_path} is on a read-only filesystem.")
        raise
    except ReadOnlyOtherError:
        print_err(f"{base_path} is read-only.")
        raise

    if original_file_exists:
        try:
            copy_to_temp_file(original_fd=original_fd, temp_file=temp_file, uid_gid=uid_gid)
        except FileCopyError:
            print_err(f"failed to copy {original_file} to temporary file at {temp_file}")
            raise

    # Attempt to edit the temp file as the original user.
    uid, _ = uid_gid
    run_editor(uid=uid, editor=editor, path=temp_file)

    handle_copy_from_temp_file(
        temp_file=temp_file,
        original_fd=original_fd,
        original_path=original_file,
        uid_gid=uid_gid,
        original_file_exists=original_file_exists,
        immutable=immutable,
    )
    os.close(original_fd)


class InvalidArgumentsError(Exception):
    """Arguments to script are invalid."""


def parse_args(args: Sequence[str]) -> tuple[str, str, str]:
    """Parse command-line arguments, raising error if too few or too many."""
    EXPECTED_ARGS = 3
    if len(args) < EXPECTED_ARGS:
        print("run0edit_inner.py: Error: too few arguments", file=sys.stderr)
        raise InvalidArgumentsError
    if len(args) > EXPECTED_ARGS:
        print("run0edit_inner.py: Error: too many arguments", file=sys.stderr)
        raise InvalidArgumentsError
    return args[0], args[1], args[2]


def remove_temp_file(
    temp_file: str, *, uid_gid: tuple[int, int], only_if_empty: bool = False
) -> None:
    """Delete the temporary file (as the specified UID and GID)."""
    temp_dir, temp_filename = os.path.split(temp_file)
    temp_parent_dir, temp_dir_name = os.path.split(temp_dir)
    uid, gid = uid_gid
    try:
        os.setegid(gid)
        os.seteuid(uid)
        temp_parent_dirfd = get_dir_fd(temp_parent_dir)
        temp_dirfd = get_dir_fd(temp_dir_name, dir_fd=temp_parent_dirfd)
        temp_fd = os.open(
            temp_filename, os.O_CLOEXEC | os.O_NOFOLLOW | os.O_PATH, dir_fd=temp_dirfd
        )
        if only_if_empty and os.fstat(temp_fd).st_size > 0:
            return
        os.close(temp_fd)
        os.unlink(temp_filename, dir_fd=temp_dirfd)
        os.rmdir(temp_dir_name, dir_fd=temp_parent_dirfd)
    except OSError:
        print_err(f"Warning: failed to remove temporary directory {temp_dir}")
    finally:
        os.seteuid(os.getuid())
        os.setegid(os.getgid())


def main(args: Sequence[str]) -> int:
    """Main function."""
    try:
        original_file, temp_file, editor = parse_args(args)
    except InvalidArgumentsError:
        return 2
    uid = int(os.environ["SUDO_UID"])
    gid = int(os.environ["SUDO_GID"])
    debug = os.environ.get("RUN0EDIT_DEBUG") == "1"
    prompt_immutable = os.environ.get("RUN0EDIT_NO_PROMPT") != "1"
    try:
        run(original_file, temp_file, editor, uid_gid=(uid, gid), prompt_immutable=prompt_immutable)
    except Run0editError:
        remove_temp_file(temp_file, uid_gid=(uid, gid), only_if_empty=True)
        if debug:
            raise
        return 1
    remove_temp_file(temp_file, uid_gid=(uid, gid))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
