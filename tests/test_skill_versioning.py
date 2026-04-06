# -*- coding: utf-8 -*-
import pytest
from api.services.skill_router import SkillRouter

# --- Unit tests for SkillRouter ---

def test_v1_client_gets_outdated_warning():
    router = SkillRouter(current_version=2)
    warnings = router.get_warnings(client_version=1, skill_id="stock-query")
    assert len(warnings) == 1
    assert "outdated" in warnings[0].lower()

def test_v2_client_no_warnings():
    router = SkillRouter(current_version=2)
    warnings = router.get_warnings(client_version=2, skill_id="stock-query")
    assert warnings == []

def test_unsupported_version_is_not_supported():
    router = SkillRouter(current_version=2)
    assert not router.is_supported(0)

def test_min_supported_version_is_supported():
    router = SkillRouter(current_version=2)
    assert router.is_supported(1)


# --- Integration tests for v1 and v2 endpoints ---

@pytest.mark.asyncio
async def test_v2_execute_includes_warnings_for_old_skill_version():
    from httpx import AsyncClient, ASGITransport
    from unittest.mock import patch, AsyncMock, MagicMock
    from api.main import app
    from api.middleware.auth import get_current_user
    from api.models.user import User, UserTier, UserRole
    from api.services.skill_actions import stock_query

    pro_user = MagicMock(spec=User)
    pro_user.id = 1
    pro_user.email = "pro@example.com"
    pro_user.tier = UserTier.PRO
    pro_user.role = UserRole.USER
    pro_user.is_active = True

    app.dependency_overrides[get_current_user] = lambda: pro_user
    try:
        with patch.object(stock_query, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"stocks": []}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/skill/v2/execute",
                    headers={
                        "Authorization": "Bearer fake",
                        "X-Skill-Version": "1",
                    },
                    json={"skill_id": "stock-query", "action": "search",
                          "version": 1, "params": {"query": "test"}},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    assert "warnings" in body
    assert len(body["warnings"]) > 0
    assert "outdated" in body["warnings"][0].lower()


@pytest.mark.asyncio
async def test_v1_endpoint_still_works_and_has_no_warnings():
    """v1 must remain functional and NOT include warnings field."""
    from httpx import AsyncClient, ASGITransport
    from unittest.mock import patch, AsyncMock, MagicMock
    from api.main import app
    from api.middleware.auth import get_current_user
    from api.models.user import User, UserTier, UserRole
    from api.services.skill_actions import stock_query

    free_user = MagicMock(spec=User)
    free_user.id = 2
    free_user.email = "free@example.com"
    free_user.tier = UserTier.FREE
    free_user.role = UserRole.USER
    free_user.is_active = True

    app.dependency_overrides[get_current_user] = lambda: free_user
    try:
        with patch.object(stock_query, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"stocks": []}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/skill/v1/execute",
                    headers={"Authorization": "Bearer fake"},
                    json={"skill_id": "stock-query", "action": "search",
                          "version": 1, "params": {"query": "test"}},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    assert "warnings" not in body  # v1 never returns warnings


@pytest.mark.asyncio
async def test_v2_current_version_client_no_warnings():
    """v2 client calling v2 endpoint gets no warnings."""
    from httpx import AsyncClient, ASGITransport
    from unittest.mock import patch, AsyncMock, MagicMock
    from api.main import app
    from api.middleware.auth import get_current_user
    from api.models.user import User, UserTier, UserRole
    from api.services.skill_actions import stock_query

    pro_user = MagicMock(spec=User)
    pro_user.id = 1
    pro_user.email = "pro@example.com"
    pro_user.tier = UserTier.PRO
    pro_user.role = UserRole.USER
    pro_user.is_active = True

    app.dependency_overrides[get_current_user] = lambda: pro_user
    try:
        with patch.object(stock_query, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"stocks": []}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                resp = await ac.post(
                    "/api/skill/v2/execute",
                    headers={
                        "Authorization": "Bearer fake",
                        "X-Skill-Version": "2",
                    },
                    json={"skill_id": "stock-query", "action": "search",
                          "version": 2, "params": {"query": "test"}},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body.get("warnings", []) == []
