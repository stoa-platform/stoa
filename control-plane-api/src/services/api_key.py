"""API Key generation and validation service"""
import secrets
import hashlib
from typing import Tuple


class APIKeyService:
    """Service for generating and validating API keys"""

    # Key format: stoa_sk_{32 random hex chars}
    KEY_PREFIX = "stoa_sk_"
    KEY_LENGTH = 32  # 32 hex chars = 128 bits of entropy

    @classmethod
    def generate_key(cls) -> Tuple[str, str, str]:
        """
        Generate a new API key.

        Returns:
            Tuple of (full_key, key_hash, key_prefix)
            - full_key: The complete API key to give to the user (shown once)
            - key_hash: SHA-256 hash to store in database
            - key_prefix: First 8 characters for display/reference
        """
        # Generate random hex string
        random_part = secrets.token_hex(cls.KEY_LENGTH // 2)

        # Build the full key
        full_key = f"{cls.KEY_PREFIX}{random_part}"

        # Hash for storage
        key_hash = cls.hash_key(full_key)

        # Prefix for reference (first 8 chars of the key)
        key_prefix = full_key[:8]

        return full_key, key_hash, key_prefix

    @classmethod
    def hash_key(cls, api_key: str) -> str:
        """
        Hash an API key using SHA-256.

        Args:
            api_key: The full API key to hash

        Returns:
            Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(api_key.encode('utf-8')).hexdigest()

    @classmethod
    def validate_format(cls, api_key: str) -> bool:
        """
        Validate the format of an API key.

        Args:
            api_key: The API key to validate

        Returns:
            True if format is valid, False otherwise
        """
        if not api_key:
            return False

        if not api_key.startswith(cls.KEY_PREFIX):
            return False

        # Check length
        expected_length = len(cls.KEY_PREFIX) + cls.KEY_LENGTH
        if len(api_key) != expected_length:
            return False

        # Check that the random part is valid hex
        random_part = api_key[len(cls.KEY_PREFIX):]
        try:
            int(random_part, 16)
            return True
        except ValueError:
            return False

    @classmethod
    def mask_key(cls, api_key: str) -> str:
        """
        Mask an API key for display (show prefix and last 4 chars).

        Args:
            api_key: The full API key

        Returns:
            Masked key like "stoa_sk_...abcd"
        """
        if len(api_key) < 12:
            return "***"
        return f"{api_key[:8]}...{api_key[-4:]}"


# Singleton instance
api_key_service = APIKeyService()
