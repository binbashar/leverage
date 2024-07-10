import pytest
from typing import List
from leverage.modules.terraform import handle_apply_arguments_parsing


class TestHandleApplyArgumentsParsing:
    @pytest.mark.parametrize(
        "input_args, expected_output",
        [
            # Test case: No arguments
            (
                [],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                ],
            ),
            # Test case: -var="my_variable=test"
            (
                ["-var=my_variable=test"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-var=my_variable=test",
                ],
            ),
            # Test case: -var-file="varfile.tfvars"
            (
                ["-var-file=varfile.tfvars"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-var-file=varfile.tfvars",
                ],
            ),
            # Test case: -target="module.appgw.0"
            (
                ["-target=module.appgw.0"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-target=module.appgw.0",
                ],
            ),
            # Test case: -target "module.appgw.0"
            (
                ["-target", "module.appgw.0"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-target",
                    "module.appgw.0",
                ],
            ),
            # Test case: -lock=false
            (
                ["-lock=false"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-lock=false",
                ],
            ),
            # Test case: -parallelism=4
            (
                ["-parallelism=4"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-parallelism=4",
                ],
            ),
            # Test case: -compact-warnings
            (
                ["-compact-warnings"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-compact-warnings",
                ],
            ),
            # Test case: -input=false
            (
                ["-input=false"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-input=false",
                ],
            ),
            # Test case: -json
            (
                ["-json"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-json",
                ],
            ),
            # Test case: -lock-timeout=60
            (
                ["-lock-timeout=60"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-lock-timeout=60",
                ],
            ),
            # Test case: -json -auto-approve
            (
                ["-json", "-auto-approve"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-json",
                    "-auto-approve",
                ],
            ),
            # Test case: -no-color
            (
                ["-no-color"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-no-color",
                ],
            ),
            # Test case: -json -no-color my_plan
            (["-json", "-no-color", "my_plan"], ["-json", "-no-color", "my_plan"]),
            # Test case: -target=helm_release.cluster_autoscaling
            (
                ["-target=helm_release.cluster_autoscaling"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-target=helm_release.cluster_autoscaling",
                ],
            ),
            # Test case: -target helm_release.cluster_autoscaling
            (
                ["-target", "helm_release.cluster_autoscaling"],
                [
                    "-var-file=/project/apps-devstg/config/backend.tfvars",
                    "-var-file=/project/apps-devstg/config/account.tfvars",
                    "-target",
                    "helm_release.cluster_autoscaling",
                ],
            ),
        ],
    )
    def test_handle_apply_arguments_parsing(self, input_args: List[str], expected_output: List[str]):
        default_args = [
            "-var-file=/project/apps-devstg/config/backend.tfvars",
            "-var-file=/project/apps-devstg/config/account.tfvars",
        ]
        assert handle_apply_arguments_parsing(default_args, input_args) == expected_output
