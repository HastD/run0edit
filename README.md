`run0edit` is to
[`run0`](https://www.freedesktop.org/software/systemd/man/257/run0.html) what
`sudoedit` is to `sudo` (in its most basic usage).

`run0edit` allows a permitted user to edit a file as root. Authorization uses
the same mechanism as `run0`, which typically takes the form of a password
prompt. The file (if it already exists) is copied to a temporary location and
opened in an unprivileged editor; if modified, the edited file contents are
copied back to the original location when the editor is closed.

If the editor exits with an abnormal status code or copying the data back to the
original location fails, then the temporary file will be left in the `/tmp`
directory. The name of the temporary file is derived from the name of the
original file, with a randomly generated suffix to avoid conflicts with existing
files.

The editor used may be customized by writing the path to your text editor of
choice (for example, `/usr/bin/vim`) to either of the files
`/etc/run0edit/editor.conf` or `/usr/share/run0edit/editor.conf`. If this does
not point to an executable file, `run0edit` will default to `nano` or `vi`, or,
in the event that neither of these are available, to prompting the user for a
path to a text editor.

Usage:

```sh
run0edit "path/to/file"
```

Currently `run0edit` does not support any other options.
