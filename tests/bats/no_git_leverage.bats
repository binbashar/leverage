setup(){
    # Resolved through BATS_LIB_PATH
    bats_load_library bats-support
    bats_load_library bats-assert

    # A directory holding nothing but the leverage entry point, to be used as the whole PATH.
    # The cli looks for git through `shutil.which`, which resolves it via PATH, and the console
    # script has an absolute shebang, so its interpreter remains reachable.
    GITLESS_PATH="$BATS_TEST_TMPDIR/gitless"
    mkdir -p "$GITLESS_PATH"
    ln -sf "$(command -v leverage)" "$GITLESS_PATH/leverage"
}

@test "Does not run if git is not installed in the system" {
    run env PATH="$GITLESS_PATH" leverage

    assert_failure
    assert_output "No git installation found in the system. Exiting."
}
