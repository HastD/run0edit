Name:           run0edit
Version:        0.4.4
Release:        1
Summary:        run0edit allows a permitted user to edit a file as root.

License:        Apache-2.0
URL:            https://github.com/HastD/%{name}
Source:         %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3
Requires:       systemd

%description
%{name} is to run0 what sudoedit is to sudo.

%{name} allows a permitted user to edit a file as root. Authorization uses
the same mechanism as run0, which typically takes the form of a password
prompt. The file (if it already exists) is copied to a temporary location and
opened in an unprivileged editor; if modified, the edited file contents are
copied back to the original location when the editor is closed.

%prep
%autosetup

%build
python3 build.py

%install
mkdir -p %{buildroot}%{_bindir} %{buildroot}%{_sysconfdir}/%{name}
install -m 755 %{name} %{buildroot}%{_bindir}/%{name}

%files
%{_bindir}/%{name}

%changelog
* 2025-05-22: v0.4.4:
  - Fixed bug in immutable flag parsing.
  - Added RPM spec.
  - Added CI workflow to build .rpm and .deb packages.
* 2025-05-17: v0.4.3:
  - Refactored to reduce code duplication and make control flow clearer.
  - Separated out the main script and outer script to separate files, with a
    Python build script to reassemble them for installation.
  - Improved message text.
* 2025-05-15: v0.4.1: Support immutable flag on directory as well.
* 2025-05-14: v0.4.0:
  - Added support for editing files with the immutable flag set by temporarily
    removing the flag and reapplying it afterward.
  - Parse arguments according to shell utility conventions, including --help
    and --version arguments with -h and -v short forms.
* 2025-03-17: v0.3.3:
  - Refactored inner script for clarity.
  - Improved sandboxing logic.
  - Bail out early if target file is read-only.
  - Style fixes to pass ShellCheck linter.
* 2025-03-16: v0.3.1:
  - Fixed handling of files in locations not readable by the user.
  - Reset PATH to default value for security.
  - Improved error messages and handling of editor selection.
* 2025-03-13: v0.2.0:
  - Switched to config files instead of environment variable for text editor selection.
  - Added systemd sandboxing to inner privileged script.
* 2025-03-10: v0.1.1: Improved error messages, added --help command.
* 2025-02-21: v0.1.0: Initial release.
