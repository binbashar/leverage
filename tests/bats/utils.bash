#! /usr/bin/env bash

_create_directory_structure(){
    : " Create a temporary directory structure like:
            root
              └ account
        And print the root path
    "
    ROOT_DIR=$(mktemp -d /tmp/tmpXXXXX)
    LEAF_DIR="$ROOT_DIR/account"
    mkdir -p $LEAF_DIR
    echo $ROOT_DIR
}

_create_leverage_directory_structure(){
    : " Create a temporary directory structure, initialize
        a git repository in the root of such structrue and
        print its path
    "
    ROOT_DIR="$(_create_directory_structure)"
    cd $ROOT_DIR
    git init >/dev/null 2>&1
    echo $ROOT_DIR
}
