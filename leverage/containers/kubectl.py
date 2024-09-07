import os
from pathlib import Path

from click.exceptions import Exit
from docker.types import Mount
from simple_term_menu import TerminalMenu

from leverage import logger
from leverage._utils import chain_commands, AwsCredsEntryPoint, ExitError, CustomEntryPoint
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
        logger.info("Retrieving k8s cluster information...")
        # generate the command that will configure the new cluster
        with CustomEntryPoint(self, entrypoint=""):  # can't recall why this change
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
            raise ExitError(exit_code, output)

        aws_eks_cmd = next(op for op in output.split("\r\n") if op.startswith("aws eks update-kubeconfig"))
        return aws_eks_cmd + f" --region {self.region}"

    def _scan_clusters(self):
        """
        Scan all the subdirectories in search of "cluster" layers.
        """
        for root, dirs, files in os.walk(self.paths.cwd):
            # exclude hidden directories
            dirs[:] = [d for d in dirs if not d[0] == "."]

            if "cluster" in dirs:
                cluster_path = Path(root) / "cluster"
                try:
                    self.paths.check_for_cluster_layer(cluster_path)
                except ExitError as exc:
                    logger.error(exc)
                else:
                    yield cluster_path

    def discover(self):
        clusters = [str(c) for c in self._scan_clusters()]
        if not clusters:
            raise ExitError(1, "No clusters found.")
        terminal_menu = TerminalMenu(clusters, title="Clusters found:")
        menu_entry_index = terminal_menu.show()
        if menu_entry_index is None:
            # selection cancelled
            return

        cluster_path = Path(clusters[menu_entry_index])
        # cluster is the host path, so in order to be able to run commands in that layer
        # we need to convert it into a relative inside the container
        self.container_config["working_dir"] = (
            self.paths.guest_base_path / cluster_path.relative_to(self.paths.cwd)
        ).as_posix()
        # TODO: rather than overriding property by propery, maybe a custom .paths object pointing to cluster_path?
        self.paths.cwd = cluster_path
        self.paths.account_config_dir = self.paths._account_config_dir(cluster_path)
        self.paths.account_conf = self.paths.account_conf_from_layer(cluster_path)
        self.configure()
