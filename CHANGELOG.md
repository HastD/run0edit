# Changelog

## [Unreleased]

Rewrote script in Python.

### Added

- Added an `--editor` option to allow the user to choose a different text
  editor. This must be an absolute path to an executable file, and the filename
  will be passed as the first argument to it.
- Added a `--no-prompt` option to skip the prompt asking the user to confirm
  whether they want to remove the immutable attribute from a file to edit it.
- Allow the user to pass multiple file paths to `run0edit`, which will be edited
  one after the other (like if you pass multiple paths to `sudoedit`).

### Changed

- Fail _before_ asking for a password if it can be determined that the parent
  directory of the file path definitely does not exist or is not valid.
- Switched to using a separate file for the inner script, which will now be
  installed at `/usr/libexec/run0edit/run0edit_inner.py`. This path will be
  passed to the `run0` invocation rather than embedding the entire inner script
  contents in an argument to `run0`. As an extra check, the SHA-256 hash of this
  file is compared against the expected value.
- Only use `/etc/run0edit/editor.conf` as a configuration file, as the secondary
  configuration path at `/usr/etc/run0edit/editor.conf` was pretty much
  redundant.
- Fail with an error message if the config file is nonempty and contains an
  invalid path. Previously this was silently ignored, defaulting to a fallback
  editor.
- Minor changes to the wording of error messages and the `--help` text.
- Stricter seccomp filters for the inner script.

### Testing and CI

- Added unit tests with 100% test coverage.
- Added GitHub workflows that automatically run Ruff (including Flake8, Pylint,
  McCabe complexity checker, and Bandit lints) for all Python versions 3.9
  through 3.13, mypy, the unit tests, and a unit test coverage check on every
  pushed commit.

## [v0.4.4] - 2025-05-22

- Fixed bug in immutable flag parsing.
- Added RPM spec.
- Added CI workflow to build `.rpm` and `.deb` packages.

## [v0.4.3] - 2025-05-17

- Refactored to reduce code duplication and make control flow clearer.
- Separated out the main script and outer script to separate files, with a
  Python build script to reassemble them for installation.
- Improved message text.

## [v0.4.1] - 2025-05-15

- Support immutable flag on directory as well.

## [v0.4.0] - 2025-05-14

- Added support for editing files with the immutable flag set by temporarily
  removing the flag and reapplying it afterward.
- Parse arguments according to shell utility conventions, including `--help` and
  `--version` arguments with `-h` and `-v` short forms.

## [v0.3.3] - 2025-03-17

- Refactored inner script for clarity.
- Improved sandboxing logic.
- Bail out early if target file is read-only.
- Style fixes to pass ShellCheck linter.

## [v0.3.1] - 2025-03-16

- Fixed handling of files in locations not readable by the user.
- Reset `PATH` to default value for security.
- Improved error messages and handling of editor selection.

## [v0.2.0] - 2025-03-13

- Switched to config files instead of environment variable for text editor
  selection.
- Added systemd sandboxing to inner privileged script.

## [v0.1.1] - 2025-03-10

- Improved error messages, added `--help` command.

## [v0.1.0] - 2025-02-21

- Initial release.

[Unreleased]: https://github.com/HastD/run0edit/compare/v0.4.4...HEAD
[v0.4.4]: https://github.com/HastD/run0edit/compare/v0.4.3...v0.4.4
[v0.4.3]: https://github.com/HastD/run0edit/compare/v0.4.1...v0.4.3
[v0.4.1]: https://github.com/HastD/run0edit/compare/v0.4.0...v0.4.1
[v0.4.0]: https://github.com/HastD/run0edit/compare/v0.3.3...v0.4.0
[v0.3.3]: https://github.com/HastD/run0edit/compare/v0.3.1...v0.3.3
[v0.3.1]: https://github.com/HastD/run0edit/compare/v0.2.0...v0.3.1
[v0.2.0]: https://github.com/HastD/run0edit/compare/v0.1.1...v0.2.0
[v0.1.1]: https://github.com/HastD/run0edit/compare/v0.1.0...v0.1.1
[v0.1.0]: https://github.com/HastD/run0edit/releases/tag/v0.1.0
