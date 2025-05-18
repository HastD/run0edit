#!/bin/sh
# shellcheck disable=SC3040
( set -o pipefail 2> /dev/null ) && set -o pipefail
set -eu
# shellcheck disable=SC2016
PATH=$(command -p env -i sh -c 'echo "$PATH"')
filename="$1"
tmpfile="$2"
editor="$3"
edit_immutable='no'

readonly_filesystem() {
    if command -v findmnt >/dev/null; then
        findmnt -nru -o OPTIONS --target "$1" | tr ',' '\n' | grep -q '^ro$'
    else
        false
    fi
}

is_immutable() {
    immutable_flag=$(lsattr -d -- "$1" 2>/dev/null | cut -d ' ' -f1 | tr -d '-' || echo '')
    [ "$immutable_flag" = 'i' ]
}

ask_immutable() {
    echo "WARNING: $1 has the immutable flag."
    if [ -d "$1" ]; then
        printf 'Temporarily remove the flag to create a file in the directory? [y/N] '
    else
        printf 'Temporarily remove the flag to edit the file? [y/N] '
    fi
    ask_immutable_response=''
    read -r ask_immutable_response
    case "$ask_immutable_response" in
        y*|Y*) true ;;
        *) false ;;
    esac
}

# If the file does not exist, ensure the directory exists and is writable.
if [ ! -e "$filename" ]; then
    directory="$(dirname -- "$filename")"
    if [ ! -d "$directory" ]; then
        echo 'run0edit: invalid argument: directory does not exist'
        exit 1
    elif [ ! -w "$directory" ]; then
        if readonly_filesystem "$directory"; then
            echo "run0edit: $directory is on a read-only filesystem."
            exit 1
        elif is_immutable "$directory"; then
            if ask_immutable "$directory"; then
                edit_immutable='yes'
            else
                echo 'run0edit: user declined to remove immutable flag; exiting.'
                exit
            fi
        else
            echo "run0edit: $directory is read-only."
            exit 1
        fi
    fi
fi

# If the file exists, ensure it is a regular file and writable, then
# attempt to copy it to the temp file.
if [ -e "$filename" ]; then
    if [ ! -f "$filename" ]; then
        echo 'run0edit: invalid argument: not a regular file'
        exit 1
    elif [ ! -w "$filename" ]; then
        if readonly_filesystem "$filename"; then
            echo "run0edit: $filename is on a read-only filesystem."
            exit 1
        elif is_immutable "$filename"; then
            if ask_immutable "$filename"; then
                edit_immutable='yes'
            else
                echo 'run0edit: user declined to remove immutable flag; exiting.'
                exit
            fi
        else
            echo "run0edit: $filename is read-only."
            exit 1
        fi
    fi
    if ! cp -- "$filename" "$tmpfile"; then
        echo "run0edit: failed to copy $filename to temporary file at $tmpfile"
        exit 1
    fi
fi

# Attempt to edit the temp file as the original user.
if ! run0 --user="$SUDO_UID" -- "$editor" "$tmpfile"; then
    echo "run0edit: failed to edit temporary file at $tmpfile"
    exit 1
fi

# If the target file exists and has been modified in the temp file, or
# if this is a new file that is non-empty, copy temp file to target.
if [ -f "$filename" ]; then
    if ! cmp -s -- "$tmpfile" "$filename"; then
        if [ "$edit_immutable" = 'yes' ]; then
            chattr -i -- "$filename"
            set +e
            cp -- "$tmpfile" "$filename"
            cp_exit_status="$?"
            set -e
            chattr +i -- "$filename"
            echo 'File edited and immutable flag reapplied.'
        else
            set +e
            cp -- "$tmpfile" "$filename"
            cp_exit_status="$?"
            set -e
        fi
        if [ "$cp_exit_status" != 0 ]; then
            echo "run0edit: unable to write temporary file at $tmpfile to $filename"
            exit 1
        elif [ "$edit_immutable" = 'yes' ] && ! cmp -s -- "$tmpfile" "$filename"; then
            echo "WARNING: contents of $filename does not match contents of edited tempfile."
            echo 'File contents may be corrupted!'
            exit 1
        fi
    else
        echo "run0edit: $filename unchanged"
    fi
else
    if [ -s "$tmpfile" ]; then
        if [ "$edit_immutable" = 'yes' ]; then
            chattr -i -- "$directory"
            touch -- "$filename"
            set +e
            cp -- "$tmpfile" "$filename"
            cp_exit_status="$?"
            set -e
            chattr +i -- "$directory"
            echo 'File created and immutable flag reapplied to directory.'
        else
            touch -- "$filename"
            set +e
            cp -- "$tmpfile" "$filename"
            cp_exit_status="$?"
            set -e
        fi
        if [ "$cp_exit_status" != 0 ]; then
            echo "run0edit: unable to write temporary file at $tmpfile to $filename"
            exit 1
        elif [ "$edit_immutable" = 'yes' ] && ! cmp -s -- "$tmpfile" "$filename"; then
            echo "WARNING: contents of $filename does not match contents of tempfile."
            echo 'File contents may be corrupted!'
            exit 1
        fi
    else
        echo "run0edit: $filename not created"
    fi
fi
