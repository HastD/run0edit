#!/usr/bin/env python3

"""Inner script for run0edit. Not meant to be run directly."""

import filecmp
import os
import pathlib
import resource
import shutil
import subprocess  # nosec
import sys

from typing import Final, Union

FILENAME: Final[str] = sys.argv[1]
TEMP_FILE: Final[str] = sys.argv[2]
EDITOR: Final[str] = sys.argv[3]
DEBUG: Final[bool] = 4 < len(sys.argv) and sys.argv[4] == "--debug"

DIRECTORY: Final[str] = os.path.dirname(FILENAME)


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


def is_immutable(path: str) -> bool:
    """Determine if the file or directory at the path has the immutable attribute."""
    lsattr_cmd = find_command("lsattr")
    if lsattr_cmd is None:
        return False
    try:
        process = subprocess.run(
            [lsattr_cmd, "-d", path], capture_output=True, check=True, text=True
        )  # nosec
    except subprocess.CalledProcessError:
        return False
    return "i" in process.stdout.strip().split()[0]


def ask_immutable(path: str) -> bool:
    """Ask the user whether to temporarily remove the immutable attribute."""
    print(f"{path} has the immutable attribute.")
    if os.path.isdir(path):
        prompt = "Temporarily remove attribute to create a file in the directory? [y/N] "
    else:
        prompt = "Temporarily remove the attribute to edit the file? [y/N] "
    response = input(prompt)
    return response.lower().startswith("y")


def handle_readonly(path: str):
    """
    Raise appropriate errors if the path points to a read-only filesystem, has
    the immutable attribute, or is otherwise read-only.
    """
    if readonly_filesystem(path):
        raise ReadOnlyFilesystemError
    if is_immutable(path):
        if not ask_immutable(path):
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


def copy_to_temp(file_exists: bool, filename: str, directory: str, temp_filename: str) -> bool:
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
            handle_readonly(filename)
            immutable = True
        copy_file_contents(filename, temp_filename)
    else:
        if not os.path.isdir(directory):
            raise NoDirectoryError
        if not os.access(directory, os.R_OK | os.W_OK):
            handle_readonly(directory)
            immutable = True
    return immutable


def run_chattr(attribute: str, path: str):
    """Run chattr to apply attribute to path (if not None). Raises ChattrError if fails."""
    chattr_cmd = find_command("chattr")
    if chattr_cmd is None:
        raise ChattrError("Unable to find chattr command")
    try:
        subprocess.run([chattr_cmd, attribute, "--", path], check=True)  # nosec
    except subprocess.CalledProcessError as e:
        raise ChattrError from e


def copy_to_dest(filename: str, temp_filename: str, chattr_path: Union[str, None]):
    """
    Copy the contents of the temp file to the target file, manipulating the
    immutable attribute on chattr_path if provided.
    """
    if chattr_path is not None:
        run_chattr("-i", chattr_path)
    try:
        pathlib.Path(filename).touch()
        copy_file_contents(temp_filename, filename)
    finally:
        if chattr_path is not None:
            run_chattr("+i", chattr_path)
            print("Immutable attribute reapplied.")
            if not filecmp.cmp(temp_filename, filename):
                raise FileContentsMismatchError


def handle_copy_to_temp(file_exists: bool) -> bool:
    """
    Copy to temp file, handling errors.
    Returns if immutable attribute should be manipulated in later step.
    """
    base_path = FILENAME if file_exists else DIRECTORY
    try:
        return copy_to_temp(file_exists, FILENAME, DIRECTORY, TEMP_FILE)
    except NotRegularFileError as e:
        print("run0edit: invalid argument: not a regular file")
        raise e
    except NoDirectoryError as e:
        print("run0edit: invalid argument: directory does not exist")
        raise e
    except FileCopyError as e:
        print(f"run0edit: failed to copy {FILENAME} to temporary file at {TEMP_FILE}")
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


def handle_copy_to_dest(file_exists: bool, immutable: bool):
    """
    If the target file exists and has been modified in the temp file, or
    if this is a new file that is non-empty, copy temp file to target.
    Handle errors or manipulate immutable attribute if needed.
    """
    if file_exists:
        if not filecmp.cmp(TEMP_FILE, FILENAME):
            chattr_path = FILENAME if immutable else None
        else:
            print(f"run0edit: {FILENAME} unchanged")
            return
    else:
        if os.path.getsize(TEMP_FILE) > 0:
            chattr_path = DIRECTORY if immutable else None
        else:
            print(f"run0edit: {FILENAME} not created")
            return
    try:
        copy_to_dest(FILENAME, TEMP_FILE, chattr_path)
    except FileCopyError as e:
        print(f"run0edit: unable to write temporary file at {TEMP_FILE} to {FILENAME}")
        raise e
    except ChattrError as e:
        print(f"run0edit: failed to run chattr on {chattr_path}")
        print("WARNING: the immutable attribute may have been removed!")
        raise e
    except FileContentsMismatchError as e:
        print(f"WARNING: contents of {FILENAME} does not match contents of edited tempfile.")
        print("File contents may be corrupted!")
        raise e


def main():
    """Main function. Raises Run0editError if a step fails."""
    file_exists = os.path.exists(FILENAME)
    try:
        immutable = handle_copy_to_temp(file_exists)
    except ReadOnlyImmutableError:
        # User declined to remove immutable attribute; exit normally.
        return

    # Attempt to edit the temp file as the original user.
    run0_cmd = find_command("run0")
    if run0_cmd is None:
        raise EditTempFileError("Unable to call run0 to start unprivileged editor process.")
    uid = int(os.environ["SUDO_UID"])
    try:
        subprocess.run([run0_cmd, f"--user={uid}", "--", EDITOR, TEMP_FILE], check=True)  # nosec
    except subprocess.CalledProcessError as e:
        print(f"run0edit: failed to edit temporary file at {TEMP_FILE}")
        raise EditTempFileError from e

    handle_copy_to_dest(file_exists, immutable)


if __name__ == "__main__":
    if DEBUG:
        main()
    else:
        try:
            main()
        except Run0editError:
            sys.exit(1)
