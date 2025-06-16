#!/usr/bin/env python3

"""Unit tests for run0edit."""

import os
import shutil
import tempfile
from typing import Final, Union

TEMP_FILE_PREFIX: Final[str] = "run0edit-unittest-"


def new_test_file(contents: bytes = b"", *, mode: Union[int, None] = None) -> str:
    """Make a temporary file with the given contents."""
    path = tempfile.mkstemp(prefix=TEMP_FILE_PREFIX)[1]
    if contents:
        with open(path, "wb") as f:
            f.write(contents)
    if mode is not None:
        os.chmod(path, mode)
    return path


def remove_test_file(path: str):
    """Remove the temporary file, changing permissions if necessary."""
    if not os.path.basename(path).startswith(TEMP_FILE_PREFIX):  # pragma: no cover
        raise ValueError("invalid filename - this doesn't look like a test file")
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def new_test_dir() -> str:
    """Make a temporary directory."""
    return tempfile.mkdtemp(prefix=TEMP_FILE_PREFIX)


def remove_test_dir(path: str):
    """Remove the temporary directory and all its contents."""
    if not os.path.basename(path).startswith(TEMP_FILE_PREFIX):  # pragma: no cover
        raise ValueError("invalid directory name - this doesn't look like a test directory")
    shutil.rmtree(path)
