import click

from leverage.container import LeverageContainer, get_docker_client


@click.command()
@click.option("--mount", multiple=True, type=click.Tuple([str, str]))
@click.option("--env-var", multiple=True, type=click.Tuple([str, str]))
def generic(mount, env_var):
    """
    Run a shell in a generic container. It supports mounting local paths and injecting arbitrary environment variables.

    Syntax:
    leverage generic --mount <local-path> <container-path> --env-var <name> <value>

    Example:
    leverage generic --mount /home/user/bin/ /usr/bin/ --env-var env dev

    Both mount and env-var parameters can be provided multiple times.

    Example:
    leverage generic --mount /home/user/bin/ /usr/bin/ --mount /etc/config.ini /etc/config.ini --env-var init 5 --env-var env dev
    """
    if env_var:
        env_var = dict(env_var)
    container = LeverageContainer(get_docker_client(), mounts=mount, env_vars=env_var)
    container.ensure_image()

    container.start(container.SHELL)
