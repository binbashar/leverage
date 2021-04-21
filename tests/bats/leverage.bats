setup_file(){
    load '/usr/lib/node_modules/bats-support/load.bash'
    load '/usr/lib/node_modules/bats-assert/load.bash'
    # get the containing directory of this file
    # use $BATS_TEST_FILENAME instead of ${BASH_SOURCE[-1]} or $0,
    # as those will point to the bats executable's location or the preprocessed file respectively
    PROJECT_ROOT="$( cd "$( dirname "$BATS_TEST_FILENAME" )/.." >/dev/null 1>&1 && pwd )"
    # make executables in src/ visible to PATH
    PATH="$PROJECT_ROOT/leverage:$PATH"
}   # Install leverage as package
    echo -e "Installing Leverage:\n" >&3 
    pip3 install -e . >&3
    echo -e "\nRunning tests:\n" >&3
}

@test 'Prints version' {
    run leverage -v
    assert_output --regexp '^leverage [0-9]+\.[0-9]+\.[0-9]+$'

    run leverage --version
    assert_output --regexp '^leverage [0-9]+\.[0-9]+\.[0-9]+$'
}