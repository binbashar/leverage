setup(){
    # Bats modules are installed globally
    load "/bats-support/load.bash"
    load "/bats-assert/load.bash"
    
    # Store useful paths
    TEST_ROOT="$( cd "$( dirname "$BATS_TEST_FILENAME" )/.." >/dev/null 2>&1 && pwd )"
    
    # Import utils
    load "utils"
}

teardown(){
    cd "$TESTS_ROOT"
}

@test "Pulls terraform image and prints version" {
    ROOT_DIR=$(_create_leverage_directory_structure)

    # Create required build.env in root directory and go there
    echo "PROJECT=ts" > "$ROOT_DIR/build.env"
    cd "$ROOT_DIR"

    run leverage terraform version

    assert_output --regexp "[\S\s]*Terraform v[0-9]{1,2}\.[0-9]{1,2}\.[0-9]{1,2}[\s\S]*"
}