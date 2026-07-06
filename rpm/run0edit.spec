# SPDX-FileCopyrightText: (c) 2025-2026 run0edit authors <https://github.com/HastD/run0edit>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

Name:           run0edit
Version:        0.5.10
Release:        2
Summary:        run0edit allows a permitted user to edit a file as root.

License:        Apache-2.0 OR MIT
URL:            https://github.com/HastD/%{name}
Source0:        https://github.com/HastD/%{name}/archive/refs/tags/v%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  meson
BuildRequires:  pandoc
BuildRequires:  python3-devel >= 3.10
Requires:       python3 >= 3.10
Requires:       systemd >= 256
Recommends:     e2fsprogs

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
%meson -Dunit-tests=disabled
%meson_build

%install
%meson_install

%files
%{_bindir}/%{name}
%{_libexecdir}/%{name}
%config(noreplace) %{_sysconfdir}/%{name}
%license %{_defaultlicensedir}/%{name}
%{_mandir}/man1/%{name}.1*

%changelog
* Sun Jul 05 2026 Daniel Hast <hast.daniel@protonmail.com> - v0.5.10
- Switch to using Meson build system.
- Add man page.
- Ignore comments and empty lines in editor.conf file.

* Wed May 06 2026 Daniel Hast <hast.daniel@protonmail.com> - v0.5.9
- Make the global configuration file higher priority than environment variables
  for editor selection.

* Thu Mar 12 2026 Daniel Hast <hast.daniel@protonmail.com> - v0.5.8
- Make temporary files have same base filename as the original file.
- Allow non-absolute editor specifications in environment variables.

* Wed Feb 11 2026 Daniel Hast <hast.daniel@protonmail.com> - v0.5.7
- Allow specifying editor via environment variables.
- Use BLAKE2 instead of SHA-256 for inner script checksum.

* Mon Dec 22 2025 Daniel Hast <hast.daniel@protonmail.com> - v0.5.6
- Add editor config file to RPM spec so it's automatically created with the
  expected permissions on install.

* Tue Oct 28 2025 Daniel Hast <hast.daniel@protonmail.com> - v0.5.5
- Add `--background` option to set or disable background color.

* Wed Oct 15 2025 Daniel Hast <hast.daniel@protonmail.com> - v0.5.4
- Increase minimum required Python version to 3.10.
- Improve error messages.

* Mon Aug 18 2025 Daniel Hast <hast.daniel@protonmail.com> - v0.5.3
- Exit with an error if config file exists but is unreadable.

* Sat Jun 21 2025 Daniel Hast <hast.daniel@protonmail.com> v0.5.2
- Fixed sandbox bug.
- Fixed SELinux denying certain custom editors.

* Tue Jun 17 2025 Daniel Hast <hast.daniel@protonmail.com> - v0.5.1
- Warn about likely incorrect usage with first argument that looks like a
  command name.

* Mon Jun 16 2025 Daniel Hast <hast.daniel@protonmail.com> - v0.5.0
- Rewrote script in Python

* Thu May 22 2025 Daniel Hast <hast.daniel@protonmail.com> - v0.4.4
- Initial RPM release
