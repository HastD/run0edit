# SPDX-FileCopyrightText: Copyright 2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

fs = import('fs')
fs.copyfile('integration_tests.py')

if get_option('integration-tests').enabled()
    test(
        'integration-test',
        find_program('uv'),
        args: ['run', 'pytest', '-v', 'integration-test/integration_tests.py'],
    )
endif
