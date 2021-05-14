setup_file(){
    # Install leverage as package
    echo -e "Installing Leverage:\n" >&3 
    pip3 install -e . >&3
    echo -e "\nRunning tests:\n" >&3
}

setup(){
    # Bats modules are installed globally
    load "/usr/lib/node_modules/bats-support/load.bash"
    load "/usr/lib/node_modules/bats-assert/load.bash"

    # Store useful paths
    TESTS_ROOT="$( cd "$( dirname "$BATS_TEST_FILENAME" )/.." >/dev/null 2>&1 && pwd )"
    BUILD_SCRIPTS="$TESTS_ROOT/build_scripts"

    # Import utils
    load "utils"
}

teardown(){
    cd "$TESTS_ROOT"
}

@test "Prints version" {
    VERSION_REGEX="^leverage, version [0-9]+\.[0-9]+\.[0-9]+$"

    run leverage --version

    assert_output --regexp $VERSION_REGEX
}

@test "Lists tasks with build script in current directory" {
    ROOT_DIR=$(_create_leverage_directory_structure)

    # Copy build script to account directory and go there
    ACC_DIR="$ROOT_DIR/account"
    cp "$BUILD_SCRIPTS/simple_build.py" "$ACC_DIR/build.py"
    cd "$ACC_DIR"

    run leverage -l

    assert_line --index 0 "Tasks in build file \`build.py\`:"
    assert_line --index 1 --regexp "^  hello\s+Say hello.\s+$"
    assert_line --index 2 --regexp "^Powered by Leverage [0-9]+.[0-9]+.[0-9]+$"
}

@test "Lists tasks with build script in parent directory" {
    ROOT_DIR=$(_create_leverage_directory_structure)

    # Copy build script to root directory and go there
    cp "$BUILD_SCRIPTS/simple_build.py" "$ROOT_DIR/build.py"
    cd "$ROOT_DIR/account"

    run leverage -l

    assert_line --index 0 "Tasks in build file \`build.py\`:"
    assert_line --index 1 --regexp "^  hello\s+Say hello.\s+$"
    assert_line --index 2 --regexp "^Powered by Leverage [0-9]+.[0-9]+.[0-9]+$"
}

@test "Simple task runs correctly" {
    ROOT_DIR=$(_create_leverage_directory_structure)
    
    # Copy build script to root directory and go there
    cp "$BUILD_SCRIPTS/simple_build.py" "$ROOT_DIR/build.py"
    cd "$ROOT_DIR"

    run leverage run hello

    assert_output --partial "Hello"
    assert_line --index 0 "[ build.py - Starting task \`hello\` ]"
    assert_line --index 1 "[ build.py - Completed task \`hello\` ]"
}

@test "Values are loaded from .env file in current directory" {
    ROOT_DIR=$(_create_leverage_directory_structure)
    ACC_DIR="$ROOT_DIR/account"

    # .env file in account directory with USE_VERBOSE_HELLO=false
    cp "$BUILD_SCRIPTS/load_env_build.py" "$ROOT_DIR/build.py"
    echo "USE_VERBOSE_HELLO=false" > "$ACC_DIR/build.env"
    cd "$ACC_DIR"

    run leverage run confhello

    assert_output --partial "Hello"
}

@test "Values are loaded from .env file in parent directory" {
    ROOT_DIR=$(_create_leverage_directory_structure)
    
    # .env file in root directory with USE_VERBOSE_HELLO=false
    cp "$BUILD_SCRIPTS/load_env_build.py" "$ROOT_DIR/build.py"
    echo "USE_VERBOSE_HELLO=false" > "$ROOT_DIR/build.env"
    cd "$ROOT_DIR/account"

    run leverage run confhello

    assert_output --partial "Hello"
}

@test "Values are loaded from .env files both in current and parent directory" {
    ROOT_DIR=$(_create_leverage_directory_structure)
    ACC_DIR="$ROOT_DIR/account"

    # .env file in root directory with USE_VERBOSE_HELLO=false
    # .env file in account directory with USE_VERBOSE_HELLO=true (should override root .env)
    cp "$BUILD_SCRIPTS/load_env_build.py" "$ROOT_DIR/build.py"
    echo "USE_VERBOSE_HELLO=false" > "$ROOT_DIR/build.env"
    echo "USE_VERBOSE_HELLO=true" > "$ACC_DIR/build.env"
    cd "$ACC_DIR"

    run leverage run confhello

    assert_output --partial "This is a way too long hello for anyone to say"
}
