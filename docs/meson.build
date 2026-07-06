# SPDX-FileCopyrightText: (c) 2026 run0edit authors <https://github.com/HastD/run0edit>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

pandoc = find_program('pandoc')

md_manpage = configure_file(
    input: 'run0edit.1.md.in',
    output: 'run0edit.1.md',
    configuration: conf_data,
)

custom_target(
    'manpage',
    input: md_manpage,
    output: 'run0edit.1',
    command: [
        pandoc,
        '-s',
        '-f', 'markdown-smart',
        '-t', 'man',
        '-o', '@OUTPUT@',
        '@INPUT@',
    ],
    build_by_default: true,
    install: true,
    install_dir: mandir / 'man1',
)
