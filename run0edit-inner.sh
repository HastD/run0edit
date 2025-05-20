#!/bin/sh
# shellcheck disable=SC3040
( set -o pipefail 2> /dev/null ) && set -o pipefail
set -eu
# shellcheck disable=SC2016
PATH=$(command -p env -i sh -c 'echo "$PATH"')
readonly filename="$1"
readonly tmpfile="$2"
readonly editor="$3"

readonly_filesystem() {
    findmnt -nru -o OPTIONS --target "$1" 2>/dev/null | tr ',' '\n' | grep -q '^ro$'
}

is_immutable() {
    case "$(lsattr -d -- "$1" 2>/dev/null | cut -d ' ' -f1 || echo '')" in
        *i*) true ;;
        *) false ;;
    esac
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

handle_readonly() {
    handle_readonly_retval='no'
    if readonly_filesystem "$1"; then
        echo "run0edit: $1 is on a read-only filesystem."
        exit 1
    elif is_immutable "$1"; then
        if ask_immutable "$1"; then
            handle_readonly_retval='yes'
        else
            echo 'run0edit: user declined to remove immutable flag; exiting.'
            exit
        fi
    else
        echo "run0edit: $1 is read-only."
        exit 1
    fi
}

copy_to_dest() {
    readonly chattr_target_path="$1"
    readonly edit_immutable="$2"
    if [ "$edit_immutable" = 'yes' ]; then
        chattr -i -- "$chattr_target_path"
    fi
    touch -- "$filename"
    set +e
    cp -- "$tmpfile" "$filename"
    cp_exit_status="$?"
    set -e
    if [ "$edit_immutable" = 'yes' ]; then
        chattr +i -- "$chattr_target_path"
        echo 'Immutable flag reapplied.'
    fi
    if [ "$cp_exit_status" != 0 ]; then
        echo "run0edit: unable to write temporary file at $tmpfile to $filename"
        exit 1
    elif [ "$edit_immutable" = 'yes' ] && ! cmp -s -- "$tmpfile" "$filename"; then
        echo "WARNING: contents of $filename does not match contents of edited tempfile."
        echo 'File contents may be corrupted!'
        exit 1
    fi
}

immutable='no'
if [ -e "$filename" ]; then
    # If the file exists, ensure it is a regular file and writable, then
    # attempt to copy it to the temp file.
    if [ ! -f "$filename" ]; then
        echo 'run0edit: invalid argument: not a regular file'
        exit 1
    elif [ ! -w "$filename" ]; then
        handle_readonly "$filename"
        immutable="$handle_readonly_retval"
    fi
    if ! cp -- "$filename" "$tmpfile"; then
        echo "run0edit: failed to copy $filename to temporary file at $tmpfile"
        exit 1
    fi
else
    # If the file does not exist, ensure the directory exists and is writable.
    directory="$(dirname -- "$filename")"
    if [ ! -d "$directory" ]; then
        echo 'run0edit: invalid argument: directory does not exist'
        exit 1
    elif [ ! -w "$directory" ]; then
        handle_readonly "$directory"
        immutable="$handle_readonly_retval"
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
        copy_to_dest "$filename" "$immutable"
    else
        echo "run0edit: $filename unchanged"
    fi
else
    if [ -s "$tmpfile" ]; then
        copy_to_dest "$directory" "$immutable"
    else
        echo "run0edit: $filename not created"
    fi
fi
