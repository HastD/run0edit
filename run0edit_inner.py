#!/usr/bin/env python3

"""
Inner script for run0edit. Not meant to be run directly.

Please report issues at: https://github.com/HastD/run0edit/issues

Copyright (C) 2025 Daniel Hast

SPDX-License-Identifier: MIT OR Apache-2.0

-----

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the “Software”), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

-----

Licensed under the Apache License, Version 2.0 (the "License").
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

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


def readonly_filesystem(path: str) -> Union[bool, None]:
    """Determine if the path is on a read-only filesystem."""
    # pylint: disable=duplicate-code
    try:
        return bool(os.statvfs(path).f_flag & os.ST_RDONLY)
    except OSError:
        return None


def find_command(command: str) -> str:
    """Search for command using a default path."""
    # pylint: disable=duplicate-code
    cmd_path = shutil.which(command, path="/usr/bin:/bin")
    if cmd_path is None:
        raise CommandNotFoundError(command)
    return cmd_path


def run_command(cmd: str, *args: str, capture_output: bool = False) -> Union[str, None]:
    """Run command as subprocess."""
    run_args = [find_command(cmd)] + list(args)
    try:
        result = subprocess.run(
            run_args, check=True, shell=False, capture_output=capture_output, text=capture_output
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
        result = run_command("lsattr", "-d", "--", path, capture_output=True)
    except SubprocessError:
        return False
    return result is not None and "i" in result.strip().split(maxsplit=1)[0]


def should_remove_immutable(path: str, is_dir: bool) -> bool:
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
        if prompt_immutable and not should_remove_immutable(path, is_dir):
            raise ReadOnlyImmutableError
    else:
        raise ReadOnlyOtherError
    return True


def handle_check_readonly(path: str, is_dir: bool, *, prompt_immutable: bool = True) -> bool:
    """Call check_readonly, handling errors."""
    try:
        return check_readonly(path, is_dir=is_dir, prompt_immutable=prompt_immutable)
    except ReadOnlyFilesystemError:
        print(f"run0edit: {path} is on a read-only filesystem.")
        raise
    except ReadOnlyImmutableError:
        print("run0edit: user declined to remove immutable attribute; exiting.")
        raise
    except ReadOnlyOtherError:
        print(f"run0edit: {path} is read-only.")
        raise


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
        # control whether O_CREAT is set, otherwise the sticky bit on /tmp
        # prevents us from writing to a file we don't own (even as root).
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


def copy_to_immutable_original(original_file: str, temp_file: str, *, original_file_exists: bool):
    """
    Copy the contents of the temp file to the target file, manipulating the immutable attribute.
    """
    chattr_path = original_file if original_file_exists else os.path.dirname(original_file)
    run_chattr("-i", chattr_path)
    try:
        copy_file_contents(temp_file, original_file, create=not original_file_exists)
    finally:
        run_chattr("+i", chattr_path)
        print("Immutable attribute reapplied.")
    filecmp.clear_cache()
    try:
        if not filecmp.cmp(temp_file, original_file, shallow=False):
            raise FileContentsMismatchError
    except OSError as e:
        raise FileContentsMismatchError from e


def copy_to_original(
    original_file: str, temp_file: str, *, original_file_exists: bool, immutable: bool
):
    """
    Copy the contents of the temp file to the target file, manipulating the
    immutable attribute if necessary.
    """
    if immutable:
        copy_to_immutable_original(
            original_file, temp_file, original_file_exists=original_file_exists
        )
    else:
        copy_file_contents(temp_file, original_file, create=not original_file_exists)


def should_copy_to_original(
    original_file: str, temp_file: str, *, original_file_exists: bool
) -> bool:
    """Determine if the temp file needs to be copied to the original file."""
    if original_file_exists:
        should_copy = not filecmp.cmp(temp_file, original_file, shallow=False)
    else:
        should_copy = os.path.getsize(temp_file) > 0
    return should_copy


def handle_copy_to_original(
    original_file: str, temp_file: str, *, original_file_exists: bool, immutable: bool
):
    """
    If the target file exists and has been modified in the temp file, or
    if this is a new file that is non-empty, copy temp file to target.
    Handle errors or manipulate immutable attribute if needed.
    """
    if not should_copy_to_original(
        original_file, temp_file, original_file_exists=original_file_exists
    ):
        print(f"run0edit: {original_file} {'unchanged' if original_file_exists else 'not created'}")
        return
    try:
        copy_to_original(
            original_file, temp_file, original_file_exists=original_file_exists, immutable=immutable
        )
    except FileCopyError:
        print(
            f"run0edit: unable to copy contents of temporary file at {temp_file} to {original_file}"
        )
        raise
    except ChattrError:
        chattr_path = original_file if original_file_exists else os.path.dirname(original_file)
        print(f"run0edit: failed to run chattr on {chattr_path}")
        print("WARNING: the immutable attribute may have been removed!")
        raise
    except FileContentsMismatchError:
        print(f"WARNING: contents of {original_file} does not match contents of edited tempfile.")
        print("File contents may be corrupted!")
        raise


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


def run(
    original_file: str, temp_file: str, editor: str, uid: int, *, prompt_immutable: bool = True
):
    """
    Copy file to temp file, run editor, and copy temp file back to target file.
    Raises Run0editError if a step fails.
    """
    original_file = os.path.realpath(original_file)
    original_file_exists = check_file_exists(original_file)
    try:
        base_path = original_file if original_file_exists else os.path.dirname(original_file)
        immutable = handle_check_readonly(
            base_path, is_dir=not original_file_exists, prompt_immutable=prompt_immutable
        )
    except ReadOnlyImmutableError:
        # User declined to remove immutable attribute; exit normally.
        return

    if original_file_exists:
        try:
            copy_file_contents(original_file, temp_file, create=False)
        except FileCopyError:
            print(f"run0edit: failed to copy {original_file} to temporary file at {temp_file}")
            raise

    # Attempt to edit the temp file as the original user.
    run_editor(uid=uid, editor=editor, path=temp_file)

    handle_copy_to_original(
        original_file, temp_file, original_file_exists=original_file_exists, immutable=immutable
    )


class InvalidArgumentsError(Exception):
    """Arguments to script are invalid."""


def parse_args(args: Sequence[str]) -> tuple[str, str, str, bool]:
    """Parse command-line arguments, raising error if too few or too many."""
    if len(args) < 3:
        print("run0edit_inner.py: Error: too few arguments")
        raise InvalidArgumentsError
    debug_str = "--debug"
    debug = len(args) == 4 and args[3] == debug_str
    if (len(args) == 4 and args[3] != debug_str) or len(args) > 4:
        print("run0edit_inner.py: Error: too many arguments")
        raise InvalidArgumentsError
    return args[0], args[1], args[2], debug


def main(args: Sequence[str], *, uid: Union[int, None] = None) -> int:
    """Main function."""
    try:
        original_file, temp_file, editor, debug = parse_args(args)
    except InvalidArgumentsError:
        return 2
    if uid is None:
        uid = int(os.environ["SUDO_UID"])
    try:
        run(original_file, temp_file, editor, uid)
    except Run0editError:
        if debug:
            raise
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
