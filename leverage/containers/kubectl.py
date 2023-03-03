import os
import pwd
from pathlib import Path

from click.exceptions import Exit
from docker.types import Mount

from leverage import logger
from leverage._utils import chain_commands, EmptyEntryPoint
from leverage.container import TerraformContainer


class KubeCtlContainer(TerraformContainer):
    """Container specifically tailored to run kubectl commands."""

    KUBECTL_CLI_BINARY = "/usr/local/bin/kubectl"
    KUBECTL_CONFIG_PATH = Path("/root/.kube")
    KUBECTL_CONFIG_FILE = KUBECTL_CONFIG_PATH / Path("config")

    def __init__(self, client):
        super().__init__(client)

        self.entrypoint = self.KUBECTL_CLI_BINARY

        host_config_path = str(Path.home() / Path(f".kube/{self.project}"))
        self.container_config["host_config"]["Mounts"].append(
            # the container is expecting a file named "config" here
            Mount(
                source=host_config_path,
                target=str(self.KUBECTL_CONFIG_PATH),
                type="bind",
            )
        )

    def start_shell(self):
        with EmptyEntryPoint(self):
            self._start()

    def configure(self):
        logger.info("Retrieving k8s cluster information...")
        with EmptyEntryPoint(self):
            add_eks_cluster_cmd = self._get_eks_kube_config()

        # generate the command that will: configure the new cluster, and also set the proper user on the new config file
        change_owner_cmd = self._change_kube_file_owner_cmd()
        full_cmd = chain_commands([add_eks_cluster_cmd, change_owner_cmd])

        logger.info("Configuring context...")
        with EmptyEntryPoint(self):
            exit_code, output = self._exec(full_cmd)
        if exit_code:
            logger.error(output)
            raise Exit(exit_code)

        logger.info("Done.")

    def _get_eks_kube_config(self) -> str:
        self.check_for_layer_location()

        exit_code, output = self._exec(f"{self.TF_BINARY} output")
        if exit_code:
            logger.error(output)
            raise Exit(exit_code)

        aws_eks_cmd = output.split("\n")[10]
        # assuming the cluster container is on the primary region
        return aws_eks_cmd + f" --region {self.common_conf['region_primary']}"

    def _change_kube_file_owner_cmd(self) -> str:
        user_id = os.getuid()
        user = pwd.getpwuid(user_id)
        group_id = user.pw_gid

        return f"chown {user_id}:{group_id} {self.KUBECTL_CONFIG_FILE}"

    def check_for_layer_location(self):
        super(KubeCtlContainer, self).check_for_layer_location()
        if self.cwd.parts[-1] != "cluster":
            logger.error("This command can only run at the [bold]cluster layer[/bold].")
            raise Exit(1)
