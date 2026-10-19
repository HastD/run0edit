# SPDX-FileCopyrightText: Copyright 2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

fs = import('fs')
fs.copyfile('integration_tests.py')
fs.copyfile('mock-editor.sh')

if get_option('integration-tests').enabled()
    test(
        'integration-test',
        find_program('uv'),
        args: ['run', 'pytest', 'integration-test/integration_tests.py'],
    )
endif
