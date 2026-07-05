# SPDX-FileCopyrightText: Copyright 2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

fs = import('fs')
fs.copyfile('__init__.py')
fs.copyfile('test_run0edit_common.py')
fs.copyfile('test_run0edit_inner.py')
fs.copyfile('test_run0edit_main.py')

if get_option('unit-tests').enabled()
    coverage = find_program('coverage')
    test(
        'unit-test',
        coverage,
        args: ['run', '-m', 'unittest'],
        is_parallel: false,
    )

    test(
        'unit-test-coverage',
        coverage,
        args: ['report', '-m', '--skip-empty', '--fail-under=100'],
        is_parallel: false,
    )
endif
