#! /usr/bin/env bash

_create_directory_structure(){
    : " Create a temporary directory structure like:
            root
              ├ config
              └ account
        And print the root path
    "
    ROOT_DIR=$(mktemp -d -t tmpXXXXXX)
    printf "PROJECT=ts\nTERRAFORM_IMAGE_TAG=%s\n" "$LEVERAGE_IMAGE_TAG" > $ROOT_DIR/"build.env"
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
