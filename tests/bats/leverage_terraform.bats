setup(){
    # Resolved through BATS_LIB_PATH
    bats_load_library bats-support
    bats_load_library bats-assert
    
    # Store useful paths
    TEST_ROOT="$( cd "$( dirname "$BATS_TEST_FILENAME" )/.." >/dev/null 2>&1 && pwd )"
    
    # Import utils
    load "utils"
}

teardown(){
    cd "$TESTS_ROOT"
}

@test "Prints terraform version" {
    ROOT_DIR=$(_create_leverage_directory_structure)

    # Create required build.env in root directory and go there
    cd "$ROOT_DIR"

    run leverage terraform version

    assert_output --regexp "Terraform v[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}"
}

@test "Prints tofu version" {
    ROOT_DIR=$(_create_leverage_directory_structure)

    # Create required build.env in root directory and go there
    cd "$ROOT_DIR"

    run leverage tofu version

    assert_output --regexp "OpenTofu v[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}"
}