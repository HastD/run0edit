# SPDX-FileCopyrightText: (c) 2026 run0edit authors <https://github.com/HastD/run0edit>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

project(
    'run0edit',
    version: '0.5.9',
    meson_version: '>= 1.3.0',
    license: 'Apache-2.0 OR MIT',
)

fs = import('fs')

prefixdir = get_option('prefix')
bindir = get_option('bindir')
libexecdir = prefixdir / get_option('libexecdir')
datadir = prefixdir / get_option('datadir')
sysconfdir = get_option('sysconfdir')

conf_data = configuration_data()
conf_data.set('VERSION', meson.project_version())
conf_data.set('BINDIR', bindir)
conf_data.set('LIBEXECDIR', libexecdir)
conf_data.set('SYSCONFDIR', sysconfdir)

main_script = configure_file(
    input: 'run0edit_main.py.in',
    output: 'run0edit_main.py',
    configuration: conf_data,
)

install_data(
    main_script,
    rename: 'run0edit',
    install_dir: bindir,
    install_mode: 'rwxr-xr-x',
)

fs.copyfile(
    'run0edit_inner.py',
    install: true,
    install_dir: libexecdir / meson.project_name(),
)

licensedir = get_option('licensedir')
if licensedir == ''
    licensedir = datadir / 'licenses' / meson.project_name()
endif
install_subdir('LICENSES', install_dir: licensedir, strip_directory: true)

fs.copyfile('pyproject.toml')
fs.copyfile('run0edit-local')

subdir('data')
subdir('test')
subdir('integration-test')

if get_option('unit-tests').enabled()
    ruff = find_program('ruff')
    test('format', ruff, args: ['format', '--diff', '--no-respect-gitignore'])
    test('lint', ruff, args: ['check', '--no-respect-gitignore'])
    test('type-check', find_program('ty'), args: ['check', '--no-respect-ignore-files'])
endif

summary({
    'unit-tests': get_option('unit-tests'),
    'integration-tests': get_option('integration-tests'),
})
