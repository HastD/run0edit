# SPDX-FileCopyrightText: Copyright 2025-2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

Name:           run0edit
Version:        0.5.7
Release:        1
Summary:        run0edit allows a permitted user to edit a file as root.

License:        Apache-2.0 OR MIT
URL:            https://github.com/HastD/%{name}
Source0:        https://github.com/HastD/%{name}/archive/refs/tags/v%{version}.tar.gz

BuildArch:      noarch
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

%install
%define inner_script_dir %{_libexecdir}/%{name}
%define inner_script_file %{inner_script_dir}/%{name}_inner.py

%define editor_conf_dir %{_sysconfdir}/%{name}
%define editor_conf_file %{editor_conf_dir}/editor.conf

mkdir -m 755 -p %{buildroot}%{_bindir} %{buildroot}%{inner_script_dir} %{buildroot}%{editor_conf_dir}

install -m 755 %{name}_main.py %{buildroot}%{_bindir}/%{name}
install -m 644 %{name}_inner.py %{buildroot}%{inner_script_file}

touch %{buildroot}%{editor_conf_file}
chmod 644 %{buildroot}%{editor_conf_file}

%files
%{_bindir}/%{name}
%{inner_script_dir}
%config(noreplace) %{editor_conf_dir}

%changelog
* Wed Feb 11 2026 Daniel Hast <hast.daniel@protonmail.com> v0.5.7
  - Update to version 0.5.7
* Mon Dec 22 2025 Daniel Hast <hast.daniel@protonmail.com> v0.5.6
  - Update to version 0.5.6
  - Add editor config file to RPM spec so it's automatically created with the
    expected permissions on install.
* Tue Oct 28 2025 Daniel Hast <hast.daniel@protonmail.com> v0.5.5
  - Update to version 0.5.5
* Wed Oct 15 2025 Daniel Hast <hast.daniel@protonmail.com> v0.5.4
  - Update to version 0.5.4
  - Increase minimum required Python version to 3.10.
  - Add python3-devel build dependency.
* Mon Aug 18 2025 Daniel Hast <hast.daniel@protonmail.com> v0.5.3
  - Update to version 0.5.3
  - Specify remote source URL to simplify Copr builds.
* Sat Jun 21 2025 Daniel Hast <hast.daniel@protonmail.com> v0.5.2
  - Update to version 0.5.2
* Tue Jun 17 2025 Daniel Hast <hast.daniel@protonmail.com> v0.5.1
  - Update to version 0.5.1
* Mon Jun 16 2025 Daniel Hast <hast.daniel@protonmail.com> v0.5.0
  - Update to version 0.5.0
  - Python rewrite: install Python scripts in place of old shell script
  - Fix systemd and Python version requirements
  - Add `Recommends: e2fsprogs` for immutable attribute support.
  - Remove `BuildRequires: python3` as there's no longer a build process.
* Thu May 22 2025 Daniel Hast <hast.daniel@protonmail.com> v0.4.4
  - Initial RPM release
