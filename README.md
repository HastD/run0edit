# run0edit

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

The choice of editor can be customized by writing the path to a text editor (for
example, `/usr/bin/vim`) to one of the files `/etc/run0edit/editor.conf` or
`/usr/etc/run0edit/editor.conf`. If this does not point to an executable file,
`run0edit` will default to using `nano` or `vi`.

> Note: Editors that make use of JIT compilation (such as Neovim built with
> LuaJIT) might not work: as a security measure, `run0edit` makes use of systemd
> sandboxing settings, including `MemoryDenyWriteExecute`, which prevents code
> generated dynamically at runtime from being executed.

`run0edit` can also be used to edit files that have the immutable flag set. In
this case, the user will be informed of the presence of the immutable flag and
asked whether they wish to continue editing; if so, the immutable flag will be
removed before the edited file contents are copied back to the original location
and then reapplied afterward. This introduces a brief window during which
another user could also edit the file (if they were permitted to do so if it
were not for the immutable flag), so to protect against this, the file is
compared with the edited temporary file after the immutable flag is reapplied,
and `run0edit` gives an error message if the file contents do not match.

## Installation

For installation via system package manager, .deb and .rpm packages can be
downloaded from the
[latest release](https://github.com/HastD/run0edit/releases/latest). For
automatic updates on Fedora-based distros, the package is also available in a
[Copr repository](https://copr.fedorainfracloud.org/coprs/amaranth/run0edit/).

Manual installation:

```sh
git clone https://github.com/HastD/run0edit
cd run0edit
python3 ./build.py
run0 install ./run0edit /usr/local/bin/
```

Note: `run0edit` requires systemd version 248 or newer.

## Usage

```
run0edit [--] "path/to/file"
run0edit --help | -h
run0edit --version | -v
```
