#! /usr/bin/env bats
#
# Hermetic tests of the layer lifecycle: init, plan, apply, output and destroy, on single layers and
# with --layers, against the real tofu/terraform binaries. The layers use the local backend and the
# built-in terraform_data resource, so no cloud credentials or network access are needed.

setup(){
    # Resolved through BATS_LIB_PATH
    bats_load_library bats-support
    bats_load_library bats-assert

    TESTS_ROOT="$( cd "$( dirname "$BATS_TEST_FILENAME" )/.." >/dev/null 2>&1 && pwd )"
    load "utils"

    # The cli creates ~/.aws/<project>: keep it, and anything else, out of the real home
    export HOME="$BATS_TEST_TMPDIR/home"
    mkdir -p "$HOME"
    # Wide enough that log lines with long temp paths do not wrap
    export COLUMNS=500
    export TF_IN_AUTOMATION=1

    ROOT_DIR=$(_create_local_backend_project)
    ACCOUNT_DIR="$ROOT_DIR/account"
}

teardown(){
    cd "$TESTS_ROOT"
    rm -rf "$ROOT_DIR"
}

@test "Runs the full lifecycle of a layer" {
    cd "$ACCOUNT_DIR/first"

    run leverage tofu init --skip-validation
    assert_success

    # -detailed-exitcode: 2 means there are changes, and the cli must pass it through
    run leverage tofu plan -detailed-exitcode -no-color
    assert_equal "$status" 2

    run leverage tofu apply -auto-approve -no-color
    assert_success

    run leverage tofu plan -detailed-exitcode -no-color
    assert_equal "$status" 0

    run leverage tofu destroy -auto-approve -no-color
    assert_success

    run leverage tofu plan -detailed-exitcode -no-color
    assert_equal "$status" 2
}

@test "Injects the common and account tfvars" {
    cd "$ACCOUNT_DIR/first"
    leverage tofu init --skip-validation
    leverage tofu apply -auto-approve

    run leverage tofu output -raw value

    assert_success
    assert_output "ts-account-first"
}

@test "Injects the backend config on init" {
    cd "$ACCOUNT_DIR/first"
    leverage tofu init --skip-validation
    leverage tofu apply -auto-approve

    # The state lands where backend.tfvars says, not on the default terraform.tfstate
    assert [ -f "leverage-test.tfstate" ]
    assert [ ! -f "terraform.tfstate" ]
}

@test "Does not touch AWS credentials when SSO and MFA are off" {
    cd "$ACCOUNT_DIR/first"
    leverage tofu init --skip-validation
    leverage tofu apply -auto-approve

    assert [ ! -e "$HOME/.aws/ts/config" ]
    assert [ ! -e "$HOME/.aws/ts/credentials" ]
}

@test "Applies several layers in the given order" {
    cd "$ACCOUNT_DIR"

    run leverage tofu init --skip-validation --layers first,second
    assert_success

    run leverage tofu apply -auto-approve -no-color --layers second,first
    assert_success
    # The layers run in the order given, not in alphabetical order
    assert_line --index 0 --partial "Invoking command for layer $ACCOUNT_DIR/second"
    assert_output --partial "Invoking command for layer $ACCOUNT_DIR/first"

    cd "$ACCOUNT_DIR/first"
    run leverage tofu output -raw value
    assert_output "ts-account-first"

    cd "$ACCOUNT_DIR/second"
    run leverage tofu output -raw value
    assert_output "ts-account-second"
}

@test "Stops at the first failing layer" {
    cd "$ACCOUNT_DIR"
    leverage tofu init --skip-validation --layers first,second
    printf 'resource "terraform_data" "broken" { input = var.undeclared }\n' > second/broken.tf

    run leverage tofu apply -auto-approve -no-color --layers second,first

    assert_failure
    assert_output --partial "Invoking command for layer $ACCOUNT_DIR/second"
    refute_output --partial "Invoking command for layer $ACCOUNT_DIR/first"
    assert [ ! -f "first/leverage-test.tfstate" ]
}

@test "Refuses --layers inside a layer" {
    cd "$ACCOUNT_DIR/first"

    run leverage tofu plan --layers second

    assert_failure
    assert_output --partial "Can not set --layers inside a layer"
}

@test "Refuses a layer that does not exist" {
    cd "$ACCOUNT_DIR"

    run leverage tofu plan --layers first,missing

    assert_failure
    assert_output --partial "does not exist or is not a directory"
}

@test "Validates the layout on init unless told to skip it" {
    cd "$ACCOUNT_DIR/first"

    # The layout validation expects an S3 backend; this layer has a local one
    run leverage tofu init

    assert_failure
    assert [ ! -d ".terraform" ]
}

@test "Runs the full lifecycle of a layer with terraform" {
    cd "$ACCOUNT_DIR/first"

    run leverage terraform init --skip-validation
    assert_success

    run leverage terraform apply -auto-approve -no-color
    assert_success

    run leverage terraform output -raw value
    assert_output "ts-account-first"

    run leverage terraform destroy -auto-approve -no-color
    assert_success
}
