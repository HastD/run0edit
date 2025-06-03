#!/usr/bin/env python3

"""Inner script for run0edit. Not meant to be run directly."""

import filecmp
import os
import resource
import stat
import shutil
import subprocess  # nosec
import sys

from collections.abc import Sequence
from typing import Union


class Run0editError(Exception):
    """Base class for run0edit errors."""


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


class CommandNotFoundError(Run0editError):
    """An external command was not found."""


class SubprocessError(Run0editError):
    """An external command failed."""


class ChattrError(Run0editError):
    """Changing immutable attribute failed."""


class FileContentsMismatchError(Run0editError):
    """File contents are not what they should be."""


def readonly_filesystem(path: str) -> Union[bool, None]:
    """Determine if the path is on a read-only filesystem."""
    # pylint: disable=duplicate-code
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return None


def find_command(command: str) -> Union[str, None]:
    """Search for command using a default path."""
    # pylint: disable=duplicate-code
    return shutil.which(command, path=os.defpath)


def run_command(cmd: str, *args: str, capture_output: bool = False) -> Union[str, None]:
    """Run command as subprocess."""
    cmd_path = find_command(cmd)
    if cmd_path is None:
        raise CommandNotFoundError(f"Command {cmd} not found")
    run_args = [cmd_path] + list(args)
    text = True if capture_output else None
    try:
        result = subprocess.run(
            run_args, check=True, shell=False, capture_output=capture_output, text=text
        )  # nosec
    except subprocess.CalledProcessError as e:
        raise SubprocessError from e
    if capture_output:
        return result.stdout
    return None


def check_file_exists(path: str) -> bool:
    """
    Test whether a file exists at the given path. Raises exception if path is a
    directory or parent of path is not a directory.
    """
    parent = os.path.dirname(path)
    try:
        stat_result = os.lstat(path)
    except FileNotFoundError as e:
        if not os.path.lexists(parent):
            print("run0edit: invalid argument: directory does not exist")
            raise NoDirectoryError(f"{parent} does not exist") from e
        return False
    except NotADirectoryError as e:
        print("run0edit: invalid argument: directory does not exist")
        raise NoDirectoryError(f"{parent} is not a directory") from e
    if not stat.S_ISREG(stat_result.st_mode):
        print("run0edit: invalid argument: not a regular file")
        raise NotRegularFileError(f"{path} is not a regular file")
    return True


def is_immutable(path: str) -> bool:
    """Determine if the file or directory at the path has the immutable attribute."""
    try:
        result = run_command("lsattr", "-d", path, capture_output=True)
    except SubprocessError:
        return False
    return result is not None and "i" in result.strip().split()[0]


def ask_immutable(path: str, is_dir: bool) -> bool:
    """Ask the user whether to temporarily remove the immutable attribute."""
    print(f"{path} has the immutable attribute.")
    if is_dir:
        prompt = "Temporarily remove attribute to create a file in the directory? [y/N] "
    else:
        prompt = "Temporarily remove the attribute to edit the file? [y/N] "
    response = input(prompt)
    return response.lower().startswith("y")


def check_readonly(
    path: str,
    is_dir: bool,
    *,
    prompt_immutable: bool = True,
) -> bool:
    """
    Ensure the path exists and is readable and writable. Return whether the
    file or directory at the path has immutable attribute to be manipulated.
    Raise appropriate errors if read-only and editing should be cancelled.
    """
    if os.access(path, os.R_OK | os.W_OK, follow_symlinks=False):
        return False
    if readonly_filesystem(path):
        raise ReadOnlyFilesystemError
    if is_immutable(path):
        if prompt_immutable and not ask_immutable(path, is_dir):
            raise ReadOnlyImmutableError
    else:
        raise ReadOnlyOtherError
    return True


def handle_check_readonly(path: str, is_dir: bool, *, prompt_immutable: bool = True) -> bool:
    """Call check_readonly, handling errors."""
    try:
        return check_readonly(path, is_dir=is_dir, prompt_immutable=prompt_immutable)
    except ReadOnlyFilesystemError as e:
        print(f"run0edit: {path} is on a read-only filesystem.")
        raise e
    except ReadOnlyImmutableError as e:
        print("run0edit: user declined to remove immutable attribute; exiting.")
        raise e
    except ReadOnlyOtherError as e:
        print(f"run0edit: {path} is read-only.")
        raise e


def copy_file_contents(src: str, dest: str, *, create: bool):
    """
    Copy contents of src to dest. Does not copy metadata. `create` argument
    specifies whether dest *must* be newly created or *must not* be created.
    """
    flags = os.O_NOFOLLOW | os.O_TRUNC | os.O_WRONLY
    if create:
        flags |= os.O_CREAT | os.O_EXCL
    try:
        buffer_size = resource.getpagesize()
        # Manually setting the flags is necessary because we need to be able to
        # ensure O_CREAT is not set, otherwise the sticky bit on /tmp prevents
        # us from writing to a file we don't own (even as root).
        fd_dest = os.open(dest, flags, mode=0o644)
        with open(src, "rb") as f_src, os.fdopen(fd_dest, "wb") as f_dest:
            while True:
                buffer = f_src.read(buffer_size)
                if not buffer:
                    break
                f_dest.write(buffer)
    except OSError as e:
        raise FileCopyError from e


def run_chattr(attribute: str, path: str):
    """Run chattr to apply attribute to path (if not None). Raises ChattrError if fails."""
    try:
        run_command("chattr", attribute, "--", path)
    except (CommandNotFoundError, SubprocessError) as e:
        raise ChattrError from e


def copy_to_dest(filename: str, temp_filename: str, *, file_exists: bool, immutable: bool):
    """
    Copy the contents of the temp file to the target file, manipulating the
    immutable attribute on chattr_path if provided.
    """
    if not immutable:
        copy_file_contents(temp_filename, filename, create=not file_exists)
        return

    chattr_path = filename if file_exists else os.path.dirname(filename)
    run_chattr("-i", chattr_path)
    try:
        copy_file_contents(temp_filename, filename, create=not file_exists)
    finally:
        run_chattr("+i", chattr_path)
        print("Immutable attribute reapplied.")
    filecmp.clear_cache()
    try:
        if not filecmp.cmp(temp_filename, filename, shallow=False):
            raise FileContentsMismatchError
    except OSError as e:
        raise FileContentsMismatchError from e


def handle_copy_to_dest(filename: str, temp_file: str, *, file_exists: bool, immutable: bool):
    """
    If the target file exists and has been modified in the temp file, or
    if this is a new file that is non-empty, copy temp file to target.
    Handle errors or manipulate immutable attribute if needed.
    """
    if file_exists:
        if not filecmp.cmp(temp_file, filename, shallow=False):
            chattr_path = filename if immutable else None
        else:
            print(f"run0edit: {filename} unchanged")
            return
    else:
        if os.path.getsize(temp_file) > 0:
            chattr_path = os.path.dirname(filename) if immutable else None
        else:
            print(f"run0edit: {filename} not created")
            return
    try:
        copy_to_dest(filename, temp_file, file_exists=file_exists, immutable=immutable)
    except FileCopyError as e:
        print(f"run0edit: unable to copy contents of temporary file at {temp_file} to {filename}")
        raise e
    except ChattrError as e:
        print(f"run0edit: failed to run chattr on {chattr_path}")
        print("WARNING: the immutable attribute may have been removed!")
        raise e
    except FileContentsMismatchError as e:
        print(f"WARNING: contents of {filename} does not match contents of edited tempfile.")
        print("File contents may be corrupted!")
        raise e


def run_editor(*, uid: int, editor: str, path: str):
    """Run the editor as the given UID to edit the file at the given path."""
    try:
        run_command("run0", f"--user={uid}", "--", editor, path)
    except CommandNotFoundError as e:
        print("run0edit: failed to call run0 to start editor")
        raise EditTempFileError from e
    except SubprocessError as e:
        print(f"run0edit: failed to edit temporary file at {path}")
        raise EditTempFileError from e


def run(filename: str, temp_file: str, editor: str, uid: int, *, prompt_immutable: bool = True):
    """
    Copy file to temp file, run editor, and copy temp file back to target file.
    Raises Run0editError if a step fails.
    """
    filename = os.path.realpath(filename)
    file_exists = check_file_exists(filename)
    try:
        base_path = filename if file_exists else os.path.dirname(filename)
        immutable = handle_check_readonly(
            base_path, is_dir=not file_exists, prompt_immutable=prompt_immutable
        )
    except ReadOnlyImmutableError:
        # User declined to remove immutable attribute; exit normally.
        return

    if file_exists:
        try:
            copy_file_contents(filename, temp_file, create=False)
        except FileCopyError as e:
            print(f"run0edit: failed to copy {filename} to temporary file at {temp_file}")
            raise e

    # Attempt to edit the temp file as the original user.
    run_editor(uid=uid, editor=editor, path=temp_file)

    handle_copy_to_dest(filename, temp_file, file_exists=file_exists, immutable=immutable)


def main(args: Sequence[str], *, uid: Union[int, None] = None) -> int:
    """Main function."""
    if len(args) < 4:
        return 2
    filename = args[1]
    temp_file = args[2]
    editor = args[3]
    debug = len(args) > 4 and args[4] == "--debug"
    if uid is None:
        uid = int(os.environ["SUDO_UID"])
    try:
        run(filename, temp_file, editor, uid)
    except Run0editError as e:
        if debug:
            raise e
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv))
