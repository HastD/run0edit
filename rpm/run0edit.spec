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
Requires:       systemd >= 256

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
%autochangelog
