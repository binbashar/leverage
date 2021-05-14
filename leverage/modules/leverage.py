from pathlib import Path

import click
from jinja2 import Template
from ruamel.yaml import YAML


@click.command()
def create_project():
    """ Create and prepare your Leverage project to be deployed based on the configurations provided in project.yaml file. """
    projectyaml = Path("project.yaml")
    config = YAML().load(projectyaml)

    templates = Path.cwd().rglob("*.template")
    templates = [(template, Template(template.read_text())) for template in templates]

    for location, template in templates:
        extension = "env" if location.stem == "build" else "tfvars"

        rendered_template = location.parent / f"{location.stem}.{extension}"
        rendered_template.write_text(template.render(config))
