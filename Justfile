# SPDX-FileCopyrightText: Copyright 2026 run0edit authors (https://github.com/HastD/run0edit)
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

[default]
@_default:
    just --list

build:
    mkdir -p build
    meson setup --reconfigure build -Dprefix=/usr
    meson compile -C build

clean:
    rm -rf build

test: build
    meson test -C build --verbose

manpage: build
    man -l build/docs/run0edit.1
