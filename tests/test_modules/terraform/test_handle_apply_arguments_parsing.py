import pytest

from leverage.modules.terraform import handle_apply_arguments_parsing


class TestHandleApplyArgumentsParsing:
    @pytest.mark.parametrize(
        "input_args,expected_output",
        [
            # Test case: Single '-key=value'
            (["-target=kubernetes_manifest.irfq"], ["-target=kubernetes_manifest.irfq"]),
            # Test case: '-key value'
            (["-target", "kubernetes_manifest.irfq"], ["-target", "kubernetes_manifest.irfq"]),
            # Test case: Multiple mixed arguments
            (
                ["-target", "kubernetes_manifest.irfq", "-lock=false"],
                ["-target", "kubernetes_manifest.irfq", "-lock=false"],
            ),
            # Test case: '-var' arguments should be included as is
            (["-var", "name=value"], ["-var", "name=value"]),
            # Test case: Non-flag argument
            (["some_value"], ["some_value"]),
            # Test case: Mixed '-key=value' and '-key value' with '-var'
            (
                ["-var", "name=value", "-target", "kubernetes_manifest.irfq", "-lock=false"],
                ["-var", "name=value", "-target", "kubernetes_manifest.irfq", "-lock=false"],
            ),
            # Test case: No arguments
            ([], []),
            # Test case: '-key=value' format with '-var'
            (["-var", "name=value", "-lock=false"], ["-var", "name=value", "-lock=false"]),
        ],
    )
    def test_handle_apply_arguments_parsing(self, input_args, expected_output):
        assert handle_apply_arguments_parsing(input_args) == expected_output
