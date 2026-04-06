from api.models.user import User, UserTier, UserRole


class PermissionDenied(Exception):
    pass


# skill_id -> {action -> min_tier}
SKILL_ACL: dict[str, dict[str, str]] = {
    "stock-query": {
        "search": "free",
    },
    "market-overview": {
        "daily": "free",
    },
    "tech-scan": {
        "run": "pro",
    },
    "fundamental-report": {
        "generate": "pro",
    },
}

# tier -> monthly LLM call quota (-1 = unlimited)
TIER_LLM_QUOTA: dict[str, int] = {
    "free": 0,
    "pro": 100,
    "admin": -1,
}

_TIER_RANK = {UserTier.FREE: 0, UserTier.PRO: 1}
_TIER_BY_STR = {"free": UserTier.FREE, "pro": UserTier.PRO}


class SkillPermissions:
    @staticmethod
    def check(user: User, skill_id: str, action: str) -> None:
        """Raises PermissionDenied if user lacks permission."""
        if user.role == UserRole.ADMIN:
            return
        if skill_id not in SKILL_ACL:
            raise PermissionDenied(f"Unknown skill: {skill_id}")
        actions = SKILL_ACL[skill_id]
        if action not in actions:
            raise PermissionDenied(f"Unknown action '{action}' for skill '{skill_id}'")
        required_str = actions[action]
        required = _TIER_BY_STR[required_str]
        if _TIER_RANK[user.tier] < _TIER_RANK[required]:
            raise PermissionDenied(
                f"Skill '{skill_id}:{action}' requires tier '{required_str}', "
                f"user has '{user.tier.value}'"
            )
