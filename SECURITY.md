<!--
SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)

SPDX-License-Identifier: Apache-2.0 OR MIT
-->

# Security Policy

## Reporting a Vulnerability

If you find a security vulnerability in `run0edit`, please report it privately
using [this form](https://github.com/HastD/run0edit/security/advisories/new).

## Security model

`run0edit` is an administrator tool: it can only be used by users who can
authenticate as an administrator, and who therefore could obtain root access by
using `run0` directly. This means the user session must be trusted to some
extent.

### TOCTOU issues with the temporary file

Certain [TOCTOU] issues are inherent to the design of `run0edit`. The basic
structure of `run0edit` is as follows:

1. As root, copy the target file's contents to a temporary file.
2. As the calling (typically unprivileged) user, open the temporary file in a
   text editor.
3. As root, after the editor exits, copy the temporary file's contents to the
   original file.

During the time that the temporary file is being edited, another process running
as the same user could edit, move, or delete the temporary file. The temporary
file is identified by path, not by file descriptor, so the file that is copied
back in the final step is whatever file is located at that path.

`run0edit` does do some basic validation on the temporary file: It ensures that
the temporary file is a regular file (not a symlink), is owned by the calling
user, and is singly-linked (that is, no other hardlinks to the file exist). If
you find a way to circumvent those checks, please do report it.

### Guarantees about the target file

In contrast, the target file should not be subject to the same sort of TOCTOU
issues; `run0edit` internally keeps track of this file using file descriptors,
not paths. The following properties are intended to be upheld:

- In the case where the target file already exists, the file whose contents are
  copied to a temporary file at the start is the same file that the temporary
  file's contents are copied to at the end, even if the target file is moved in
  the meantime.
- In the case where the target file does not exist and a new file is to be
  created in its parent directory, the parent directory is tracked by file
  descriptor, and a new file with the specified filename will be created in that
  same directory even if the directory is moved while the editor is open.
- If the target file exists and has the immutable attribute, the same file will
  have its immutable attribute temporarily removed and restored to allow the
  final copy operation.
- If the target file does not exist and its parent directory has the immutable
  attribute, the same directory will have its immutable attribute temporarily
  removed and restored to allow file creation, and the newly created file with
  the specified name in that directory will have the immutable attribute set on
  it.
- In both of the above cases where the immutable attribute is to be set on a
  file, if the file contents after the immutable attribute has been set are not
  the same as the contents that were written (which could happen if another
  process edits the file during the brief window during which the file does not
  have the immutable attribute), then `run0edit` will print a warning message
  informing the user of this fact.

If you find a way to circumvent these properties, please report it.

[TOCTOU]: https://en.wikipedia.org/wiki/Time-of-check_to_time-of-use
