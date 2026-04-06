import pytest
from api.services.skill_permissions import SkillPermissions, PermissionDenied
from api.models.user import User, UserTier, UserRole


def make_user(tier: UserTier, role: UserRole = UserRole.USER) -> User:
    u = User()
    u.tier = tier
    u.role = role
    return u


def test_free_user_can_access_free_skill():
    user = make_user(UserTier.FREE)
    SkillPermissions.check(user, "stock-query", "search")  # should not raise


def test_free_user_cannot_access_pro_skill():
    user = make_user(UserTier.FREE)
    with pytest.raises(PermissionDenied, match="requires tier"):
        SkillPermissions.check(user, "tech-scan", "run")


def test_pro_user_can_access_all_skills():
    user = make_user(UserTier.PRO)
    SkillPermissions.check(user, "tech-scan", "run")
    SkillPermissions.check(user, "stock-query", "search")


def test_admin_bypasses_tier_check():
    user = make_user(UserTier.FREE, UserRole.ADMIN)
    SkillPermissions.check(user, "tech-scan", "run")  # free tier but admin role


def test_unknown_skill_raises_permission_denied():
    user = make_user(UserTier.PRO)
    with pytest.raises(PermissionDenied, match="Unknown skill"):
        SkillPermissions.check(user, "nonexistent-skill", "run")


def test_unknown_action_raises_permission_denied():
    user = make_user(UserTier.PRO)
    with pytest.raises(PermissionDenied):
        SkillPermissions.check(user, "stock-query", "nonexistent-action")


def test_free_user_can_access_market_overview():
    user = make_user(UserTier.FREE)
    SkillPermissions.check(user, "market-overview", "daily")  # should not raise


def test_pro_user_can_access_fundamental_report():
    user = make_user(UserTier.PRO)
    SkillPermissions.check(user, "fundamental-report", "generate")  # should not raise


def test_free_user_cannot_access_fundamental_report():
    user = make_user(UserTier.FREE)
    with pytest.raises(PermissionDenied, match="requires tier"):
        SkillPermissions.check(user, "fundamental-report", "generate")
