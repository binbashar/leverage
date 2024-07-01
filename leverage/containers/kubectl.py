from pathlib import Path

from click.exceptions import Exit
from docker.types import Mount

from leverage import logger
from leverage._utils import AwsCredsEntryPoint, ExitError
from leverage.container import TerraformContainer


class KubeCtlContainer(TerraformContainer):
    """Container specifically tailored to run kubectl commands."""

    KUBECTL_CLI_BINARY = "/usr/local/bin/kubectl"
    KUBECTL_CONFIG_PATH = Path(f"/home/{TerraformContainer.CONTAINER_USER}/.kube")
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
        self.paths.check_for_cluster_layer()

        logger.info("Retrieving k8s cluster information...")
        # generate the command that will configure the new cluster
        with AwsCredsEntryPoint(self, override_entrypoint=""):
            add_eks_cluster_cmd = self._get_eks_kube_config()

        logger.info("Configuring context...")
        with AwsCredsEntryPoint(self, override_entrypoint=""):
            exit_code = self._start(add_eks_cluster_cmd)
        if exit_code:
            raise Exit(exit_code)

        logger.info("Done.")

    def _get_eks_kube_config(self) -> str:
        exit_code, output = self._start_with_output(f"{self.TF_BINARY} output -no-color")  # TODO: override on CM?
        if exit_code:
            raise ExitError(exit_code, output)

        aws_eks_cmd = next(op for op in output.split("\r\n") if op.startswith("aws eks update-kubeconfig"))
        return aws_eks_cmd + f" --region {self.region}"
