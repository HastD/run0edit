#!/usr/bin/env python3

"""Inner script for run0edit. Not meant to be run directly."""

import filecmp
import os
import pathlib
import resource
import shutil
import subprocess  # nosec
import sys

from typing import Sequence, Union


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


def find_command(command: str) -> Union[str, None]:
    """Search for command using a default path."""
    return shutil.which(command, path=os.defpath)


def readonly_filesystem(path: str) -> Union[bool, None]:
    """Determine if the path is on a read-only filesystem."""
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return None


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


def is_immutable(path: str) -> bool:
    """Determine if the file or directory at the path has the immutable attribute."""
    try:
        result = run_command("lsattr", "-d", path, capture_output=True)
    except SubprocessError:
        return False
    return result is not None and "i" in result.strip().split()[0]


def ask_immutable(path: str) -> bool:
    """Ask the user whether to temporarily remove the immutable attribute."""
    print(f"{path} has the immutable attribute.")
    if os.path.isdir(path):
        prompt = "Temporarily remove attribute to create a file in the directory? [y/N] "
    else:
        prompt = "Temporarily remove the attribute to edit the file? [y/N] "
    response = input(prompt)
    return response.lower().startswith("y")


def handle_readonly(path: str, *, prompt: bool = True):
    """
    Raise appropriate errors if the path points to a read-only filesystem, has
    the immutable attribute, or is otherwise read-only.
    """
    if readonly_filesystem(path):
        raise ReadOnlyFilesystemError
    if is_immutable(path):
        if prompt and not ask_immutable(path):
            raise ReadOnlyImmutableError
    else:
        raise ReadOnlyOtherError


def copy_file_contents(src: str, dest: str):
    """Copy contents of src to dest. Does not copy metadata."""
    try:
        buffer_size = resource.getpagesize()
        # Manually setting the flags is necessary because we need to ensure
        # O_CREAT is not set, otherwise the sticky bit on /tmp prevents us from
        # writing to a file we don't own (even as root).
        fd_dest = os.open(dest, os.O_WRONLY | os.O_TRUNC)
        with open(src, "rb") as f_src, os.fdopen(fd_dest, "wb") as f_dest:
            while True:
                buffer = f_src.read(buffer_size)
                if not buffer:
                    break
                f_dest.write(buffer)
    except OSError as e:
        raise FileCopyError from e


def copy_to_temp(
    file_exists: bool,
    filename: str,
    directory: str,
    temp_filename: str,
    *,
    prompt_immutable: bool = True,
) -> bool:
    """
    If the file exists, ensure it is a regular file and writable, then
    attempt to copy it to the temp file.
    If the file does not exist, ensure the directory exists and is writable.
    Return whether an immutable attribute should be manipulated.
    """
    immutable = False
    if file_exists:
        if not os.path.isfile(filename):
            raise NotRegularFileError
        if not os.access(filename, os.R_OK | os.W_OK):
            handle_readonly(filename, prompt=prompt_immutable)
            immutable = True
        copy_file_contents(filename, temp_filename)
    else:
        if not os.path.isdir(directory):
            raise NoDirectoryError
        if not os.access(directory, os.R_OK | os.W_OK):
            handle_readonly(directory, prompt=prompt_immutable)
            immutable = True
    return immutable


def run_chattr(attribute: str, path: str):
    """Run chattr to apply attribute to path (if not None). Raises ChattrError if fails."""
    try:
        run_command("chattr", attribute, "--", path)
    except CommandNotFoundError as e:
        raise ChattrError from e
    except SubprocessError as e:
        raise ChattrError from e


def copy_to_dest(filename: str, temp_filename: str, chattr_path: Union[str, None]):
    """
    Copy the contents of the temp file to the target file, manipulating the
    immutable attribute on chattr_path if provided.
    """
    if chattr_path is None:
        pathlib.Path(filename).touch()
        copy_file_contents(temp_filename, filename)
        return

    run_chattr("-i", chattr_path)
    try:
        pathlib.Path(filename).touch()
        copy_file_contents(temp_filename, filename)
    finally:
        run_chattr("+i", chattr_path)
        print("Immutable attribute reapplied.")
    try:
        if not filecmp.cmp(temp_filename, filename):
            raise FileContentsMismatchError
    except OSError as e:
        raise FileContentsMismatchError from e


def handle_copy_to_temp(
    filename: str,
    directory: str,
    temp_file: str,
    file_exists: bool,
    *,
    prompt_immutable: bool = True,
) -> bool:
    """
    Copy to temp file, handling errors.
    Returns if immutable attribute should be manipulated in later step.
    """
    base_path = filename if file_exists else directory
    try:
        return copy_to_temp(
            file_exists, filename, directory, temp_file, prompt_immutable=prompt_immutable
        )
    except NotRegularFileError as e:
        print("run0edit: invalid argument: not a regular file")
        raise e
    except NoDirectoryError as e:
        print("run0edit: invalid argument: directory does not exist")
        raise e
    except FileCopyError as e:
        print(f"run0edit: failed to copy {filename} to temporary file at {temp_file}")
        raise e
    except ReadOnlyFilesystemError as e:
        print(f"run0edit: {base_path} is on a read-only filesystem.")
        raise e
    except ReadOnlyImmutableError as e:
        print("run0edit: user declined to remove immutable attribute; exiting.")
        raise e
    except ReadOnlyOtherError as e:
        print(f"run0edit: {base_path} is read-only.")
        raise e


def handle_copy_to_dest(
    filename: str, directory: str, temp_file: str, file_exists: bool, immutable: bool
):
    """
    If the target file exists and has been modified in the temp file, or
    if this is a new file that is non-empty, copy temp file to target.
    Handle errors or manipulate immutable attribute if needed.
    """
    if file_exists:
        if not filecmp.cmp(temp_file, filename):
            chattr_path = filename if immutable else None
        else:
            print(f"run0edit: {filename} unchanged")
            return
    else:
        if os.path.getsize(temp_file) > 0:
            chattr_path = directory if immutable else None
        else:
            print(f"run0edit: {filename} not created")
            return
    try:
        copy_to_dest(filename, temp_file, chattr_path)
    except FileCopyError as e:
        print(f"run0edit: unable to write temporary file at {temp_file} to {filename}")
        raise e
    except ChattrError as e:
        print(f"run0edit: failed to run chattr on {chattr_path}")
        print("WARNING: the immutable attribute may have been removed!")
        raise e
    except FileContentsMismatchError as e:
        print(f"WARNING: contents of {filename} does not match contents of edited tempfile.")
        print("File contents may be corrupted!")
        raise e


def run(filename: str, temp_file: str, editor: str, uid: int, *, prompt_immutable: bool = True):
    """
    Copy file to temp file, run editor, and copy temp file back to target file.
    Raises Run0editError if a step fails.
    """
    file_exists = os.path.exists(filename)
    directory = os.path.dirname(filename)
    try:
        immutable = handle_copy_to_temp(
            filename, directory, temp_file, file_exists, prompt_immutable=prompt_immutable
        )
    except ReadOnlyImmutableError:
        # User declined to remove immutable attribute; exit normally.
        return

    # Attempt to edit the temp file as the original user.
    try:
        run_command("run0", f"--user={uid}", "--", editor, temp_file)
    except CommandNotFoundError as e:
        raise EditTempFileError from e
    except SubprocessError as e:
        print(f"run0edit: failed to edit temporary file at {temp_file}")
        raise EditTempFileError from e

    handle_copy_to_dest(filename, directory, temp_file, file_exists, immutable)


def main(args: Sequence[str]) -> int:
    """Main function."""
    if len(args) < 4:
        return 2
    filename = args[1]
    temp_file = args[2]
    editor = args[3]
    debug = len(args) > 4 and args[4] == "--debug"
    uid = int(os.environ["SUDO_UID"])
    try:
        run(filename, temp_file, editor, uid)
    except Run0editError as e:
        if debug:
            raise e
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
