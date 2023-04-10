import os
import pwd
from pathlib import Path

from click.exceptions import Exit
from docker.types import Mount

from leverage import logger
from leverage._utils import chain_commands, AwsCredsEntryPoint
from leverage.container import TerraformContainer


class KubeCtlContainer(TerraformContainer):
    """Container specifically tailored to run kubectl commands."""

    KUBECTL_CLI_BINARY = "/usr/local/bin/kubectl"
    KUBECTL_CONFIG_PATH = Path("/root/.kube")
    KUBECTL_CONFIG_FILE = KUBECTL_CONFIG_PATH / Path("config")

    def __init__(self, client):
        super().__init__(client)

        self.entrypoint = self.KUBECTL_CLI_BINARY

        self.host_kubectl_config_dir = Path.home() / Path(f".kube/{self.project}")
        if not self.host_kubectl_config_dir.exists():
            # make sure the folder exists before mounting it
            self.host_kubectl_config_dir.mkdir(parents=True)

        self.container_config["host_config"]["Mounts"].append(
            # the container is expecting a file named "config" here
            Mount(
                source=str(self.host_kubectl_config_dir),
                target=str(self.KUBECTL_CONFIG_PATH),
                type="bind",
            )
        )

    def start_shell(self):
        with AwsCredsEntryPoint(self):
            self._start("/bin/bash")

    def configure(self):
        # make sure we are on the cluster layer
        self.check_for_layer_location()

        logger.info("Retrieving k8s cluster information...")
        # generate the command that will configure the new cluster
        with AwsCredsEntryPoint(self):
            add_eks_cluster_cmd = self._get_eks_kube_config()
        # and the command that will set the proper ownership on the config file (otherwise the owner will be "root")
        change_owner_cmd = self._change_kube_file_owner_cmd()
        full_cmd = chain_commands([add_eks_cluster_cmd, change_owner_cmd])

        logger.info("Configuring context...")
        with AwsCredsEntryPoint(self):
            exit_code = self._start(full_cmd)
        if exit_code:
            raise Exit(exit_code)

        logger.info("Done.")

    def _get_eks_kube_config(self) -> str:
        exit_code, output = self._start_with_output(f"{self.TF_BINARY} output -no-color")
        if exit_code:
            logger.error(output)
            raise Exit(exit_code)

        aws_eks_cmd = next(op for op in output.split("\r\n") if op.startswith("aws eks update-kubeconfig"))
        return aws_eks_cmd + f" --region {self.region}"

    def _get_user_group_id(self, user_id) -> int:
        user = pwd.getpwuid(user_id)
        return user.pw_gid

    def _change_kube_file_owner_cmd(self) -> str:
        user_id = os.getuid()
        group_id = self._get_user_group_id(user_id)

        return f"chown {user_id}:{group_id} {self.KUBECTL_CONFIG_FILE}"

    def check_for_layer_location(self):
        super(KubeCtlContainer, self).check_for_layer_location()
        # assuming the "cluster" layer will contain the expected EKS outputs
        if self.cwd.parts[-1] != "cluster":
            logger.error("This command can only run at the [bold]cluster layer[/bold].")
            raise Exit(1)
