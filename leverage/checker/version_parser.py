import os
import re
from typing import Dict, Any, Union, List

import hcl2


class VersionExtractor:
    """Extracts versions from parsed Terraform configurations using best practices with type tagging."""

    @staticmethod
    def extract_versions(tf_config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        versions = {}
        VersionExtractor.extract_core_and_providers(tf_config, versions)
        VersionExtractor.extract_module_versions(tf_config, versions)
        return versions

    @staticmethod
    def extract_core_and_providers(tf_config: Dict[str, Any], versions: Dict[str, Dict[str, str]]):
        for terraform_block in tf_config.get("terraform", []):
            if isinstance(terraform_block, dict):
                if "required_version" in terraform_block:
                    versions["terraform"] = {"type": "core", "version": terraform_block["required_version"]}
                if "required_providers" in terraform_block:
                    VersionExtractor.process_providers(terraform_block["required_providers"], versions)

    @staticmethod
    def process_providers(providers: Union[Dict[str, Any], List[Dict[str, Any]]], versions: Dict[str, Dict[str, str]]):
        if isinstance(providers, dict):
            VersionExtractor.extract_provider_versions(providers, versions)
        elif isinstance(providers, list):
            for provider_dict in providers:
                VersionExtractor.extract_provider_versions(provider_dict, versions)
        else:
            print(f"Error: Providers data structure not recognized: {providers}")

    @staticmethod
    def extract_provider_versions(providers: Dict[str, Any], versions: Dict[str, Dict[str, str]]):
        for provider, details in providers.items():
            if isinstance(details, dict) and "version" in details:
                versions[provider] = {"type": "provider", "version": details["version"]}
            elif isinstance(details, str):
                versions[provider] = {"type": "provider", "version": details}

    @staticmethod
    def extract_module_versions(tf_config: Dict[str, Any], versions: Dict[str, Dict[str, str]]):
        module_version_pattern = re.compile(r"\?ref=v([\d\.]+)$")
        for module in tf_config.get("module", []):
            if isinstance(module, dict) and "source" in module:
                source = module["source"]
                match = module_version_pattern.search(source)
                if match:
                    versions[f"Module: {module['source']}"] = {"type": "module", "version": match.group(1)}
                elif "version" in module:
                    versions[f"Module: {module['source']}"] = {"type": "module", "version": module["version"]}


class TerraformFileParser:
    @staticmethod
    def load(file_path: str) -> Dict[str, Any]:
        with open(file_path, "r") as tf_file:
            return hcl2.load(tf_file)


class VersionManager:
    def __init__(self, directory: str):
        self.directory = directory

    def find_versions(self) -> Dict[str, Dict[str, str]]:
        versions = {}
        for root, _, files in os.walk(self.directory):
            for file in files:
                if file.endswith(".tf"):
                    file_path = os.path.join(root, file)
                    try:
                        tf_config = TerraformFileParser.load(file_path)
                        versions.update(VersionExtractor.extract_versions(tf_config))
                    except Exception as e:
                        self.handle_error(e, file_path)
        return versions

    @staticmethod
    def handle_error(e: Exception, file_path: str):
        print(f"Error processing {file_path}: {e}")
