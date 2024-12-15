import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from click.exceptions import Exit
from docker.types import Mount
import ruamel.yaml
import simple_term_menu

from leverage import logger
from leverage._utils import AwsCredsEntryPoint, ExitError, CustomEntryPoint
from leverage.container import TerraformContainer


@dataclass
class ClusterInfo:
    cluster_name: str
    profile: str
    region: str


class MetadataTypes(Enum):
    K8S_CLUSTER = "k8s-eks-cluster"


class KubeCtlContainer(TerraformContainer):
    """Container specifically tailored to run kubectl commands."""

    KUBECTL_CLI_BINARY = "/usr/local/bin/kubectl"
    KUBECTL_CONFIG_PATH = Path(f"/home/{TerraformContainer.CONTAINER_USER}/.kube")
    KUBECTL_CONFIG_FILE = KUBECTL_CONFIG_PATH / Path("config")
    METADATA_FILENAME = "metadata.yaml"

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

    def configure(self, ci: ClusterInfo = None):
        """
        Add the given EKS cluster configuration to the .kube/ files.
        """
        if ci:
            # if you have the details, generate the command right away
            cmd = f"aws eks update-kubeconfig --region {ci.region} --name {ci.cluster_name} --profile {ci.profile}"
        else:
            # otherwise go get them from the layer
            logger.info("Retrieving k8s cluster information...")
            with CustomEntryPoint(self, entrypoint=""):
                cmd = self._get_eks_kube_config()

        logger.info("Configuring context...")
        with AwsCredsEntryPoint(self, override_entrypoint=""):
            exit_code = self._start(cmd)

        if exit_code:
            raise Exit(exit_code)

        logger.info("Done.")

    def _get_eks_kube_config(self) -> str:
        exit_code, output = self._start_with_output(f"{self.TF_BINARY} output -no-color")  # TODO: override on CM?
        if exit_code:
            raise ExitError(exit_code, output)

        aws_eks_cmd = next(op for op in output.split("\r\n") if op.startswith("aws eks update-kubeconfig"))
        return aws_eks_cmd + f" --region {self.region}"

    def _scan_clusters(self):
        """
        Scan all the subdirectories in search of "cluster" metadata files.
        """
        for root, dirs, files in os.walk(self.paths.cwd):
            # exclude hidden directories
            dirs[:] = [d for d in dirs if d[0] != "."]

            for file in files:
                if file != self.METADATA_FILENAME:
                    continue

                cluster_file = Path(root) / file
                try:
                    with open(cluster_file) as cluster_yaml_file:
                        data = ruamel.yaml.safe_load(cluster_yaml_file)
                    if data.get("type") != MetadataTypes.K8S_CLUSTER.value:
                        continue
                except Exception as exc:
                    logger.warning(exc)
                    continue
                else:
                    yield Path(root), data

    def discover(self):
        """
        Do a scan down the tree of subdirectories looking for k8s clusters metadata files.
        Open up a menu with all the found items, where you can pick up and configure it on your .kubeconfig file.
        """
        cluster_files = [(path, data) for path, data in self._scan_clusters()]
        if not cluster_files:
            raise ExitError(1, "No clusters found.")

        terminal_menu = simple_term_menu.TerminalMenu(
            [f"{c[1]['data']['cluster_name']}: {str(c[0])}" for c in cluster_files], title="Clusters found:"
        )
        menu_entry_index = terminal_menu.show()
        if menu_entry_index is None:
            # selection cancelled
            return

        layer_path = cluster_files[menu_entry_index][0]
        cluster_data = cluster_files[menu_entry_index][1]
        cluster_info = ClusterInfo(
            cluster_name=cluster_data["data"]["cluster_name"],
            profile=cluster_data["data"]["profile"],
            region=cluster_data["data"]["region"],
        )

        # cluster is the host path, so in order to be able to run commands in that layer
        # we need to convert it into a relative inside the container
        self.container_config["working_dir"] = (
            self.paths.guest_base_path / layer_path.relative_to(self.paths.cwd)
        ).as_posix()
        # now simulate we are standing on the chosen layer folder
        self.paths.update_cwd(layer_path)
        self.configure(cluster_info)
