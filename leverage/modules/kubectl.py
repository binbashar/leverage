import os
from enum import Enum
from pathlib import Path
from dataclasses import dataclass

import click
import ruamel.yaml
import simple_term_menu

from leverage import logger
from leverage.path import PathsHandler
from leverage._utils import ExitError
from leverage.modules.aws import aws
from leverage.modules.runner import Runner
from leverage.modules.tfrunner import TFRunner
from leverage.modules.utils import _handle_subcommand
from leverage.modules.auth import _perform_authentication as perform_authentication
from leverage._internals import pass_state, pass_paths, pass_environment


@dataclass
class ClusterInfo:
    cluster_name: str
    profile: str
    region: str


class MetadataTypes(Enum):
    K8S_CLUSTER = "k8s-eks-cluster"


METADATA_FILENAME = "metadata.yaml"


@click.group(invoke_without_command=True, context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
@pass_state
@click.pass_context
def kubectl(context, state, args):
    """Run Kubectl commands in the context of the current project."""

    kubeconfig_dir = state.paths.home / ".kube" / state.paths.project
    kubeconfig_dir.mkdir(parents=True, exist_ok=True)
    state.environment["KUBECONFIG"] = str(kubeconfig_dir / "config")

    state.runner = Runner(
        binary="kubectl",
        error_message=(
            f"Kubectl not found on system. "
            f"Please install it following the instructions at: https://kubernetes.io/docs/tasks/tools/#kubectl"
        ),
        env_vars=state.environment,
    )

    authenticate = pass_paths(lambda paths: perform_authentication(paths))
    _handle_subcommand(context=context, runner=state.runner, args=args, pre_invocation_callback=authenticate)


def _configure(environment: dict, ci: ClusterInfo = None, layer_path: Path = None):
    """
    Add the given EKS cluster configuration to the .kube/ files.
    """
    if ci:
        # if you have the details, generate the command right away
        cmd = ["eks", "update-kubeconfig", "--region", ci.region, "--name", ci.cluster_name, "--profile", ci.profile]
    else:
        # otherwise go get them from the layer
        logger.info("Retrieving k8s cluster information...")
        cmd = _get_eks_kube_config(environment, layer_path).split(" ")[1:]

    logger.info("Configuring context...")
    try:
        exit_code, _, _ = Runner(binary="aws", env_vars=environment).exec(*cmd)
    except ExitError as e:
        raise ExitError(e.exit_code, f"Could not locate AWS cli binary.")
    if exit_code:
        raise ExitError(exit_code, f"Failed to configure kubectl context: {exit_code}")

    logger.info("Done.")


@pass_paths
def _get_eks_kube_config(paths: PathsHandler, environment: dict, layer_path: Path) -> str:
    # TODO: Get rid of this ugly workaround
    try:
        tfrunner = TFRunner(binary=paths.tf_binary, env_vars=environment)
    except ExitError as e:
        try:
            tfrunner = TFRunner(binary=paths.tf_binary, terraform=True, env_vars=environment)
        except ExitError:
            raise ExitError(e.exit_code, f"Could not locate TF binary.")

    perform_authentication(paths)
    exit_code, output, error = tfrunner.exec("output", "-no-color", working_dir=layer_path)
    if exit_code:
        raise ExitError(exit_code, f"Failed to get EKS kube config: {error}")

    region = paths.common_conf.get("region_primary", paths.common_conf.get("region", ""))
    if not region:
        raise ExitError(1, "No region configured in global config file.")

    aws_eks_cmd = next(op for op in output.splitlines() if op.startswith("aws eks update-kubeconfig"))
    return aws_eks_cmd + f" --region {region}"


@kubectl.command()
@pass_paths
@pass_environment
def configure(environment: dict, paths: PathsHandler):
    """Automatically add the EKS cluster from the layer into your kubectl config file."""
    paths.check_for_cluster_layer()
    _configure(environment, layer_path=paths.cwd)


def _scan_clusters(cwd: Path):
    """
    Scan all the subdirectories in search of "cluster" metadata files.
    """
    for root, dirs, files in os.walk(cwd):
        # exclude hidden directories
        dirs[:] = [d for d in dirs if d[0] != "."]

        for file in files:
            if file != METADATA_FILENAME:
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


@kubectl.command()
@pass_paths
@pass_environment
def discover(environment: dict, paths: PathsHandler):
    """
    Do a scan down the tree of subdirectories looking for k8s clusters metadata files.
    Open up a menu with all the found items, where you can pick up and configure it on your .kubeconfig file.
    """
    cluster_files = [(path, data) for path, data in _scan_clusters(paths.cwd)]
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

    _configure(environment, cluster_info, layer_path)
