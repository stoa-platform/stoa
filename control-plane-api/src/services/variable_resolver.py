"""Variable Resolver Service for GitOps templates

Resolves ${VARIABLE} placeholders in API configurations using:
1. Environment-specific config (environments/{env}.yaml)
2. API-specific overrides (apis/{api}/environments/{env}.yaml)
3. Default values (${VAR:default_value})
4. Vault references (vault:secret/path#key)
"""
import re
import logging
from typing import Optional, Any
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Pattern for ${VAR} or ${VAR:default}
VARIABLE_PATTERN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*?)(?::([^}]*))?\}')

# Pattern for vault references
VAULT_PATTERN = re.compile(r'^vault:(.+)#(.+)$')


class VariableResolver:
    """
    Resolves variables in GitOps templates.

    Variable resolution order (last wins):
    1. Global defaults (_defaults.yaml)
    2. Environment config (environments/{env}/config.yaml)
    3. API-specific environment config (apis/{api}/environments/{env}.yaml)
    4. Inline defaults (${VAR:default})
    """

    def __init__(self, vault_client=None):
        """
        Initialize resolver with optional Vault client.

        Args:
            vault_client: Optional VaultService for resolving vault: references
        """
        self._vault = vault_client
        self._cache: dict[str, dict] = {}

    def resolve_string(self, template: str, variables: dict[str, str]) -> str:
        """
        Resolve variables in a string template.

        Args:
            template: String with ${VAR} or ${VAR:default} placeholders
            variables: Dictionary of variable values

        Returns:
            Resolved string with all variables substituted

        Example:
            >>> resolver.resolve_string("${BACKEND_URL}/api", {"BACKEND_URL": "https://api.example.com"})
            'https://api.example.com/api'
        """
        def replace_var(match):
            var_name = match.group(1)
            default = match.group(2)

            value = variables.get(var_name)
            if value is not None:
                return str(value)
            elif default is not None:
                return default
            else:
                logger.warning(f"Unresolved variable: ${{{var_name}}}")
                return match.group(0)  # Keep original if not found

        return VARIABLE_PATTERN.sub(replace_var, template)

    def resolve_dict(self, template: dict, variables: dict[str, str]) -> dict:
        """
        Recursively resolve variables in a dictionary.

        Args:
            template: Dictionary that may contain ${VAR} placeholders in values
            variables: Dictionary of variable values

        Returns:
            New dictionary with all variables resolved
        """
        result = {}
        for key, value in template.items():
            if isinstance(value, str):
                result[key] = self.resolve_string(value, variables)
            elif isinstance(value, dict):
                result[key] = self.resolve_dict(value, variables)
            elif isinstance(value, list):
                result[key] = [
                    self.resolve_string(item, variables) if isinstance(item, str)
                    else self.resolve_dict(item, variables) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def merge_configs(self, *configs: dict) -> dict:
        """
        Deep merge multiple configuration dictionaries.

        Later configs override earlier ones.

        Args:
            *configs: Variable number of config dicts to merge

        Returns:
            Merged configuration dictionary
        """
        result = {}
        for config in configs:
            if config:
                result = self._deep_merge(result, config)
        return result

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    async def resolve_vault_reference(self, reference: str) -> Optional[str]:
        """
        Resolve a vault:path#key reference.

        Args:
            reference: String like "vault:secret/data/dev/api#client_secret"

        Returns:
            Secret value from Vault, or None if not found
        """
        match = VAULT_PATTERN.match(reference)
        if not match:
            return None

        path, key = match.groups()

        if not self._vault:
            logger.warning(f"Vault client not configured, cannot resolve: {reference}")
            return None

        try:
            secret = await self._vault.get_secret(path)
            return secret.get(key) if secret else None
        except Exception as e:
            logger.error(f"Failed to resolve vault reference {reference}: {e}")
            return None

    async def resolve_api_config(
        self,
        api_template: dict,
        environment: str,
        global_config: Optional[dict] = None,
        api_env_config: Optional[dict] = None,
    ) -> dict:
        """
        Fully resolve an API configuration for a specific environment.

        This is the main entry point for resolving API templates.

        Args:
            api_template: The api.yaml template with ${VAR} placeholders
            environment: Target environment (dev, staging, prod)
            global_config: Global environment config (environments/{env}/config.yaml)
            api_env_config: API-specific environment config (apis/{api}/environments/{env}.yaml)

        Returns:
            Fully resolved API configuration ready for deployment

        Example:
            >>> api_template = {"backend": {"url": "${BACKEND_URL}"}}
            >>> env_config = {"BACKEND_URL": "https://api-dev.example.com"}
            >>> result = await resolver.resolve_api_config(api_template, "dev", env_config)
            >>> result["backend"]["url"]
            'https://api-dev.example.com'
        """
        # Merge all variable sources
        variables = {}

        if global_config:
            # Extract variables section from global config
            variables.update(global_config.get("variables", global_config))

        if api_env_config:
            # API-specific overrides
            variables.update(api_env_config.get("variables", api_env_config))

        # Add standard variables
        variables["ENVIRONMENT"] = environment

        # Resolve all placeholders
        resolved = self.resolve_dict(api_template, variables)

        # Resolve any vault references in the resolved config
        resolved = await self._resolve_vault_refs_in_dict(resolved)

        return resolved

    async def _resolve_vault_refs_in_dict(self, data: dict) -> dict:
        """Recursively resolve vault: references in a dictionary."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("vault:"):
                resolved = await self.resolve_vault_reference(value)
                result[key] = resolved if resolved else value
            elif isinstance(value, dict):
                result[key] = await self._resolve_vault_refs_in_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    await self._resolve_vault_refs_in_dict(item) if isinstance(item, dict)
                    else (await self.resolve_vault_reference(item) if isinstance(item, str) and item.startswith("vault:") else item)
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def extract_variables(self, template: str) -> list[str]:
        """
        Extract all variable names from a template string.

        Args:
            template: String with ${VAR} placeholders

        Returns:
            List of variable names found

        Example:
            >>> resolver.extract_variables("${API_URL}/v1/${API_VERSION}")
            ['API_URL', 'API_VERSION']
        """
        return [match.group(1) for match in VARIABLE_PATTERN.finditer(template)]

    def extract_all_variables(self, data: Any) -> set[str]:
        """
        Extract all variable names from a nested structure.

        Args:
            data: String, dict, or list that may contain ${VAR} placeholders

        Returns:
            Set of all variable names found
        """
        variables = set()

        if isinstance(data, str):
            variables.update(self.extract_variables(data))
        elif isinstance(data, dict):
            for value in data.values():
                variables.update(self.extract_all_variables(value))
        elif isinstance(data, list):
            for item in data:
                variables.update(self.extract_all_variables(item))

        return variables

    def validate_config(self, template: dict, variables: dict[str, str]) -> list[str]:
        """
        Validate that all required variables are provided.

        Args:
            template: Template dictionary with ${VAR} placeholders
            variables: Available variables

        Returns:
            List of missing variable names (empty if all resolved)
        """
        required = self.extract_all_variables(template)
        missing = []

        for var in required:
            # Check if variable is provided or has a default in the template
            if var not in variables:
                # Check if the variable has a default value in the template
                pattern = re.compile(rf'\$\{{{var}:([^}}]*)\}}')
                has_default = False

                def check_defaults(data):
                    nonlocal has_default
                    if isinstance(data, str) and pattern.search(data):
                        has_default = True
                    elif isinstance(data, dict):
                        for v in data.values():
                            check_defaults(v)
                    elif isinstance(data, list):
                        for item in data:
                            check_defaults(item)

                check_defaults(template)

                if not has_default:
                    missing.append(var)

        return missing


# Global instance
variable_resolver = VariableResolver()
