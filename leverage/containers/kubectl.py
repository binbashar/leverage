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
        with AwsCredsEntryPoint(self, override_entrypoint=""):
            self._start(self.SHELL)

    def configure(self):
        # make sure we are on the cluster layer
        self.check_for_cluster_layer()

        logger.info("Retrieving k8s cluster information...")
        # generate the command that will configure the new cluster
        with AwsCredsEntryPoint(self, override_entrypoint=""):
            add_eks_cluster_cmd = self._get_eks_kube_config()
        # and the command that will set the proper ownership on the config file (otherwise the owner will be "root")
        change_owner_cmd = self.change_ownership_cmd(self.KUBECTL_CONFIG_FILE, recursive=False)
        full_cmd = chain_commands([add_eks_cluster_cmd, change_owner_cmd])

        logger.info("Configuring context...")
        with AwsCredsEntryPoint(self, override_entrypoint=""):
            exit_code = self._start(full_cmd)
        if exit_code:
            raise Exit(exit_code)

        logger.info("Done.")

    def _get_eks_kube_config(self) -> str:
        exit_code, output = self._start_with_output(f"{self.TF_BINARY} output -no-color")  # TODO: override on CM?
        if exit_code:
            logger.error(output)
            raise Exit(exit_code)

        aws_eks_cmd = next(op for op in output.split("\r\n") if op.startswith("aws eks update-kubeconfig"))
        return aws_eks_cmd + f" --region {self.region}"

    def check_for_cluster_layer(self):
        self.check_for_layer_location()
        # assuming the "cluster" layer will contain the expected EKS outputs
        if self.cwd.parts[-1] != "cluster":
            logger.error("This command can only run at the [bold]cluster layer[/bold].")
            raise Exit(1)
