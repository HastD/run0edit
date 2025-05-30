# Changelog

## [Unreleased]

- Rewrote script in Python.
- Switched to using separate file in `/usr/libexec` for inner script.
- Added `--editor` option to choose a different editor.
- Added unit tests.

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
