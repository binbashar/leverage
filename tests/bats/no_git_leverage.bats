# The name of the file was chosen as to avoid repetition of the leverage package installing step
# in leverage.bats, since bats respects file name order to run the tests

setup_file(){
    # Uninstall git
    apt-get remove -y git >/dev/null 2>&1
}

teardown_file(){
    # Reinstall git
    apt-get install -y git >/dev/null 2>&1
}

setup(){
    # Bats modules are installed globally
    load "/usr/lib/node_modules/bats-support/load.bash"
    load "/usr/lib/node_modules/bats-assert/load.bash"
}

@test "Does not run if git is not installed in the system" {
    run leverage

    assert_failure
    assert_output "No git installation found in the system. Exiting."
}