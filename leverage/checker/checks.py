import os
from abc import ABC, abstractmethod
from typing import List

import hcl2
import yaml


class VersionCheck(ABC):
    def __init__(self, name: str, version_rule: str):
        self.name = name
        self.version_rule = version_rule

    @abstractmethod
    def run(self) -> None:
        """Implement this method to check version compatibility"""
        pass


class CommandVersionCheck(VersionCheck):
    def __init__(self, name: str, version_rule: str):
        super().__init__(name, version_rule)
        self.modules: List[ModuleVersionCheck] = []

    def add_module(self, module: "ModuleVersionCheck") -> None:
        self.modules.append(module)

    def run(self) -> None:
        print(f"Checking command {self.name} with version rule {self.version_rule}")
        for module in self.modules:
            module.run()


class ModuleVersionCheck(VersionCheck):
    def run(self) -> None:
        print(f"Checking module {self.name} with version rule {self.version_rule}")


class CommandGroupCheck:
    def __init__(self):
        self.commands: List[CommandVersionCheck] = []

    def add_command(self, command: CommandVersionCheck) -> None:
        self.commands.append(command)

    def run(self) -> None:
        print("Running group checks for all commands...")
        for command in self.commands:
            command.run()
        print("All group checks completed successfully.")


def load_config(filename: str = "commands.yml") -> dict:
    with open(filename, "r") as file:
        data = yaml.safe_load(file)
    return data


def setup_version_check_hierarchy(config: dict) -> CommandGroupCheck:
    root_group = CommandGroupCheck()  # This will hold all top-level commands
    for cmd_info in config["commands"]:
        command = CommandVersionCheck(name=cmd_info["name"], version_rule=cmd_info["version_rule"])
        root_group.add_command(command)
        for mod_info in cmd_info.get("modules", []):
            module = ModuleVersionCheck(name=mod_info["name"], version_rule=mod_info["version_rule"])
            command.add_module(module)
    return root_group


def run_checks(check: CommandGroupCheck) -> None:
    check.run()
