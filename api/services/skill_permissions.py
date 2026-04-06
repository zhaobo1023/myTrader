from api.models.user import User, UserTier, UserRole


class PermissionDenied(Exception):
    pass


# skill_id -> {action -> min_tier}
SKILL_ACL: dict[str, dict[str, str]] = {
    "stock-query": {
        "search": UserTier.FREE.value,
    },
    "market-overview": {
        "daily": UserTier.FREE.value,
    },
    "tech-scan": {
        "run": UserTier.PRO.value,
    },
    "fundamental-report": {
        "generate": UserTier.PRO.value,
    },
}

# For admin users (role == ADMIN), quota is unlimited (-1).
# Callers should check role before calling TIER_LLM_QUOTA.get(user.tier.value, 0).
# tier -> monthly LLM call quota (-1 = unlimited)
TIER_LLM_QUOTA: dict[str, int] = {
    UserTier.FREE.value: 0,
    UserTier.PRO.value: 100,
}

# Build tier ranking dynamically from enum order to stay in sync with UserTier changes
_TIER_RANK: dict[UserTier, int] = {tier: i for i, tier in enumerate(UserTier)}
_TIER_BY_STR: dict[str, UserTier] = {tier.value: tier for tier in UserTier}


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
        try:
            required = _TIER_BY_STR[required_str]
            user_rank = _TIER_RANK[user.tier]
            required_rank = _TIER_RANK[required]
        except KeyError as e:
            raise PermissionDenied(f"Unknown tier in permission check: {e}") from e
        if user_rank < required_rank:
            raise PermissionDenied(
                f"Skill '{skill_id}:{action}' requires tier '{required_str}', "
                f"user has '{user.tier.value}'"
            )
