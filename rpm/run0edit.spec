Name:           run0edit
Version:        0.5.0
Release:        1
Summary:        run0edit allows a permitted user to edit a file as root.

License:        Apache-2.0
URL:            https://github.com/HastD/%{name}
Source:         %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3 >= 3.9
Requires:       python3 >= 3.9
Requires:       systemd >= 248

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

%install
mkdir -p %{buildroot}%{_bindir} %{buildroot}%{_libexecdir}/%{name} %{buildroot}%{_sysconfdir}/%{name}
install -m 755 %{name}_main.py %{buildroot}%{_bindir}/%{name}
install -m 644 %{name}_inner.py %{buildroot}%{_libexecdir}/%{name}/%{name}_inner.py

%files
%{_bindir}/%{name}
%{_libexecdir}/%{name}

%changelog
* Thu May 29 2025 - v0.5.0:
  - Rewrote script in Python.
  - Switched to using separate file in `/usr/libexec` for inner script.
  - Added unit tests.
* Thu May 22 2025 - v0.4.4:
  - Fixed bug in immutable flag parsing.
  - Added RPM spec.
  - Added CI workflow to build .rpm and .deb packages.
* Sat May 17 2025 - v0.4.3:
  - Refactored to reduce code duplication and make control flow clearer.
  - Separated out the main script and outer script to separate files, with a
    Python build script to reassemble them for installation.
  - Improved message text.
* Thu May 15 2025 - v0.4.1:
  - Support immutable flag on directory as well.
* Wed May 14 2025 - v0.4.0:
  - Added support for editing files with the immutable flag set by temporarily
    removing the flag and reapplying it afterward.
  - Parse arguments according to shell utility conventions, including --help
    and --version arguments with -h and -v short forms.
* Mon Mar 17 2025 - v0.3.3:
  - Refactored inner script for clarity.
  - Improved sandboxing logic.
  - Bail out early if target file is read-only.
  - Style fixes to pass ShellCheck linter.
* Sun Mar 16 2025 - v0.3.1:
  - Fixed handling of files in locations not readable by the user.
  - Reset PATH to default value for security.
  - Improved error messages and handling of editor selection.
* Thu Mar 13 2025 - v0.2.0:
  - Switched to config files instead of environment variable for text editor selection.
  - Added systemd sandboxing to inner privileged script.
* Mon Mar 10 2025 - v0.1.1:
  - Improved error messages, added --help command.
* Fri Feb 21 2025 - v0.1.0:
  - Initial release.
