import os
import re
from typing import Dict, Any

import hcl2


class VersionExtractor:
    """Extracts versions from parsed Terraform configurations, focusing on accurate source handling based on Terraform documentation."""

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
    def process_providers(providers: Any, versions: Dict[str, Dict[str, str]]):
        if isinstance(providers, dict):
            VersionExtractor.extract_provider_versions(providers, versions)
        elif isinstance(providers, list):
            for provider_dict in providers:
                VersionExtractor.extract_provider_versions(provider_dict, versions)

    @staticmethod
    def extract_provider_versions(providers: Dict[str, Any], versions: Dict[str, Dict[str, str]]):
        for provider, details in providers.items():
            if isinstance(details, dict) and "version" in details:
                versions[provider] = {"type": "provider", "version": details["version"]}
            elif isinstance(details, str):
                versions[provider] = {"type": "provider", "version": details}

    @staticmethod
    def extract_module_versions(tf_config: Dict[str, Any], versions: Dict[str, Dict[str, str]]):
        for module in tf_config.get("module", []):
            if isinstance(module, dict):
                for name, data in module.items():
                    source = data.get("source", "")
                    explicit_version = data.get("version", None)
                    version_info = VersionExtractor.parse_source(source, explicit_version)
                    versions[name] = version_info

    @staticmethod
    def parse_source(source: str, explicit_version: str = None) -> Dict[str, str]:
        # Local path detection
        if source.startswith("./") or source.startswith("../"):
            return {"type": "local", "source": source, "version": explicit_version or "N/A"}
        # GitHub URL detection (SSH or HTTPS)
        elif "github.com" in source:
            return VersionExtractor.parse_github_source(source, explicit_version)
        # Registry source detection
        elif any(x in source for x in ["terraform-registry", "registry.terraform.io"]):
            return VersionExtractor.parse_registry_source(source, explicit_version)
        else:
            return {"type": "other", "source": source, "version": explicit_version or "unknown"}

    @staticmethod
    def parse_github_source(source: str, explicit_version: str) -> Dict[str, str]:
        ref_match = re.search(r"ref=([vV]?[\w\d\.\-_]+)", source)
        version = ref_match.group(1) if ref_match else explicit_version
        if version and version.lower().startswith("v"):
            version = version[1:]  # Strip the 'v' prefix if present
        return {"type": "github", "repository": source.split("?")[0], "version": version or "HEAD"}

    @staticmethod
    def parse_registry_source(source: str, explicit_version: str) -> Dict[str, str]:
        """
        Parses Terraform Registry sources with or without a hostname.
        Formats:
        - <NAMESPACE>/<NAME>/<PROVIDER>
        - <HOSTNAME>/<NAMESPACE>/<NAME>/<PROVIDER>
        """
        regex = re.compile(r"^(?:(?P<hostname>[\w\.:-]+)/)?(?P<namespace>\w+)/(?P<name>\w+)/(?P<provider>\w+)$")
        match = regex.match(source)
        if match:
            details = match.groupdict()
            hostname = details.get("hostname")
            namespace = details["namespace"]
            name = details["name"]
            provider = details["provider"]
            module_identifier = f"{namespace}/{name}/{provider}"
            if hostname:
                module_identifier = f"{hostname}/{module_identifier}"
            version_match = re.search(r"ref=([vV]?[\w\d\.]+)", source)
            version = version_match.group(1) if version_match else explicit_version
            if version and version.lower().startswith("v"):
                version = version[1:]  # Strip the 'v' prefix if present
            return {
                "type": "registry",
                "module": module_identifier,
                "version": version or "latest",
                "hostname": hostname or "public",
            }
        return {"type": "registry", "source": source, "version": explicit_version or "unknown"}


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
