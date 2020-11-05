import subprocess
from . import path

docker_cmd = ["docker", "run", "--rm", "--workdir=/go/src/project/", "-it"]
docker_img = "binbash/terraform-awscli-slim:0.13.2"
docker_volumes = [
    "--volume=%s:/go/src/project:rw" % path.get_working_path(),
    "--volume=%s:/config" % path.get_account_config_path(),
    "--volume=%s:/common-config" % path.get_global_config_path(),
    "--volume=%s/.ssh:/root/.ssh" % path.get_home_path(),
    "--volume=%s/.gitconfig:/etc/gitconfig" % path.get_home_path(),
    "--volume=%s/.aws/bb:/root/.aws/bb" % path.get_home_path(),
]
docker_envs = [
    "--env=AWS_SHARED_CREDENTIALS_FILE=/root/.aws/bb/credentials",
    "--env=AWS_CONFIG_FILE=/root/.aws/bb/config",
]

def _build_cmd(command="", args=[], entrypoint="/bin/terraform"):
    cmd = docker_cmd + docker_volumes + docker_envs
    cmd.append("--entrypoint=%s" % entrypoint)
    cmd.append(docker_img)
    if command != "":
        cmd.append(command)
    cmd = cmd + args
    print("[DEBUG] %s" % (" ".join(cmd)))
    return cmd

def init():
    cmd = _build_cmd(command="init", args=["-backend-config=/config/backend.config"])
    return subprocess.call(cmd)

def plan():
    cmd = _build_cmd(
        command="plan",
        args=[
            "-var-file=/config/backend.config",
            "-var-file=/common-config/common.config",
            "-var-file=/config/account.config"
        ]
    )
    return subprocess.call(cmd)

def apply():
    cmd = _build_cmd(
        command="apply",
        args=[
            "-var-file=/config/backend.config",
            "-var-file=/common-config/common.config",
            "-var-file=/config/account.config"
        ]
    )
    return subprocess.call(cmd)

def output():
    cmd = _build_cmd(command="output")
    return subprocess.call(cmd)

def version():
    cmd = _build_cmd(command="version")
    return subprocess.call(cmd)

def shell():
    cmd = _build_cmd(command="", entrypoint="/bin/sh")
    return subprocess.call(cmd)
