# -*- coding: utf-8 -*-
"""
SkillRouter - version compatibility checking for skill gateway endpoints.
"""

CURRENT_GATEWAY_VERSION = 2
MIN_SUPPORTED_VERSION = 1


class SkillRouter:
    def __init__(self, current_version: int = CURRENT_GATEWAY_VERSION):
        self.current_version = current_version

    def get_warnings(self, client_version: int) -> list[str]:
        # skill_id reserved for future per-skill deprecation policy
        """Return warnings for the client based on version mismatch."""
        if client_version < MIN_SUPPORTED_VERSION:
            return [
                f"Skill version {client_version} is no longer supported. "
                f"Minimum supported version: {MIN_SUPPORTED_VERSION}."
            ]
        if client_version < self.current_version:
            return [
                f"Skill version {client_version} is outdated. "
                f"Latest gateway version: {self.current_version}. "
                f"Some features may be unavailable."
            ]
        return []

    def is_supported(self, client_version: int) -> bool:
        return client_version >= MIN_SUPPORTED_VERSION
