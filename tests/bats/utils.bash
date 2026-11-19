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

_create_local_backend_project(){
    : " Create a Leverage project whose layers need no cloud access:
            root
              ├ build.env
              ├ config/common.tfvars      project = \"ts\"
              └ account
                  ├ config
                  │   ├ account.tfvars    environment = \"account\"
                  │   └ backend.tfvars    path = \"leverage-test.tfstate\"
                  ├ first/main.tf
                  └ second/main.tf
        Each layer uses the local backend and a built-in terraform_data resource, and outputs
        <project>-<environment>-<layer>, so an output proves both tfvars files were injected.
        SSO and MFA are off, so the cli never authenticates. Print the root path.
    "
    # Resolve symlinks (macOS's TMPDIR lives under /var -> /private/var): terraform turns the
    # -backend-config path into a relative one from the real cwd, which breaks across a symlink
    ROOT_DIR="$(cd "$(_create_leverage_directory_structure)" && pwd -P)"
    printf 'project = "ts"\n' > "$ROOT_DIR/config/common.tfvars"
    mkdir -p "$ROOT_DIR/account/config"
    printf 'environment = "account"\n' > "$ROOT_DIR/account/config/account.tfvars"
    printf 'path = "leverage-test.tfstate"\n' > "$ROOT_DIR/account/config/backend.tfvars"

    for LAYER in first second; do
        mkdir -p "$ROOT_DIR/account/$LAYER"
        cat > "$ROOT_DIR/account/$LAYER/main.tf" <<HCL
terraform {
  backend "local" {}
}

variable "project" { type = string }
variable "environment" { type = string }

resource "terraform_data" "this" {
  input = "\${var.project}-\${var.environment}-$LAYER"
}

output "value" {
  value = terraform_data.this.output
}
HCL
    done
    echo $ROOT_DIR
}
