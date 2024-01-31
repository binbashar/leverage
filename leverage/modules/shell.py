import click

from leverage._utils import CustomEntryPoint
from leverage.container import get_docker_client, TerraformContainer
from leverage.modules.utils import env_var_option, mount_option, auth_sso, auth_mfa


@click.command()
@mount_option
@env_var_option
@auth_mfa
@auth_sso
def shell(mount, env_var, mfa, sso):
    """
    Run a shell in a generic container. It supports mounting local paths and injecting arbitrary environment variables.
    It also supports AWS credentials injection via mfa/sso.

    Syntax:
    leverage shell --mount <local-path> <container-path> --env-var <name> <value>

    Example:
    leverage shell --mount /home/user/bin/ /usr/bin/ --env-var env dev

    Both mount and env-var parameters can be provided multiple times.

    Example:
    leverage shell --mount /home/user/bin/ /usr/bin/ --mount /etc/config.ini /etc/config.ini --env-var init 5 --env-var env dev
    """
    if env_var:
        env_var = dict(env_var)
    # TODO: TerraformContainer is the only class supporting sso/mfa auth automagically
    #       Move this capacity into a mixin later
    container = TerraformContainer(get_docker_client(), mounts=mount, env_vars=env_var)
    container.ensure_image()

    # auth
    container.disable_authentication()
    if sso:
        container.enable_sso()
    if mfa:
        container.enable_mfa()

    with CustomEntryPoint(container, entrypoint=""):
        container._start(container.SHELL)
