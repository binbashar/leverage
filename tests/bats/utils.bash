#! /usr/bin/env bash

_create_directory_structure(){
    : " Create a temporary directory structure like:
            root
              ├ config
              └ account
        And print the root path
    "
    # An explicit template keeps the name free of dots on both GNU and BSD mktemp. `-t` yields
    # `tmp.XXXX` on macOS, and the build script is imported under a module name derived from the
    # directory, which a dot turns into a package lookup that fails.
    ROOT_DIR=$(mktemp -d "${TMPDIR:-/tmp}/leverageXXXXXX")
    printf "PROJECT=ts\n" > $ROOT_DIR/"build.env"
    mkdir -p "$ROOT_DIR/config"
    mkdir -p "$ROOT_DIR/account"
    echo $ROOT_DIR
}

_create_leverage_directory_structure(){
    : " Create a temporary directory structure, initialize
        a git repository in the root of such structure and
        print its path
    "
    ROOT_DIR="$(_create_directory_structure)"
    cd $ROOT_DIR
    git init >/dev/null 2>&1
    echo $ROOT_DIR
}
