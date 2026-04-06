# RBAC + Subscription Permission System Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement a User → Role → PermissionGroup → PermissionPoint RBAC system with subscription-driven feature gating so paid features (AI analysis, factors, research) require appropriate tier/permissions.

**Architecture:** Five new DB tables store the RBAC graph. A `PermissionChecker` FastAPI dependency is injected into any endpoint that needs gating. A seed script populates the default `free_user` / `pro_user` / `admin` roles. Tier-to-role promotion happens at subscription upgrade time.

**Tech Stack:** SQLAlchemy async ORM (existing), Alembic migration (existing), FastAPI `Depends`, MySQL InnoDB, `api/core/permissions.py` (new).

---

## Permission Model

```
User ─── user_roles ─── Role ─── role_permission_groups ─── PermissionGroup ─── group_permission_points ─── PermissionPoint
```

### Default Roles and Permission Points

| Role | PermissionGroup | PermissionPoints |
|------|----------------|-----------------|
| `free_user` | `market_basic` | `market.kline`, `market.search`, `market.latest_date` |
| `free_user` | `portfolio_basic` | `portfolio.summary`, `portfolio.history` |
| `pro_user` | (all free groups) | (all free points) |
| `pro_user` | `market_advanced` | `market.factors`, `market.indicators`, `market.rps` |
| `pro_user` | `research_all` | `research.fundamental`, `research.valuation`, `research.sentiment`, `research.composite`, `research.watchlist` |
| `pro_user` | `ai_analysis` | `ai.rag.query`, `ai.rag.report`, `ai.analysis.technical`, `ai.analysis.fundamental` |
| `admin` | `admin_all` | `admin.*` (wildcard — checked separately) |

### Wildcard Rule
A permission point of `admin.*` grants all permissions. The checker checks exact match OR prefix wildcard.

---

## New DB Tables

```sql
-- Leaf permission nodes
CREATE TABLE permission_points (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(100) NOT NULL UNIQUE COMMENT 'e.g. market.factors',
    description VARCHAR(255),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Logical groups of permissions
CREATE TABLE permission_groups (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- M2M: group -> points
CREATE TABLE group_permission_points (
    group_id   INT NOT NULL,
    point_id   INT NOT NULL,
    PRIMARY KEY (group_id, point_id),
    FOREIGN KEY (group_id) REFERENCES permission_groups(id) ON DELETE CASCADE,
    FOREIGN KEY (point_id) REFERENCES permission_points(id) ON DELETE CASCADE
);

-- Named roles
CREATE TABLE roles (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE COMMENT 'free_user / pro_user / admin',
    description VARCHAR(255),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- M2M: role -> groups
CREATE TABLE role_permission_groups (
    role_id  INT NOT NULL,
    group_id INT NOT NULL,
    PRIMARY KEY (role_id, group_id),
    FOREIGN KEY (role_id)  REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES permission_groups(id) ON DELETE CASCADE
);

-- M2M: user -> roles
CREATE TABLE user_roles (
    user_id INT NOT NULL,
    role_id INT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
);
```

---

### Task 0: Alembic migration — RBAC tables

**Files:**
- Create: `alembic/versions/b2c3d4e5f6a7_rbac_tables.py`

**Step 1: Generate migration file**

```bash
cd /Users/zhaobo/data0/person/myTrader
DB_ENV=online alembic revision --autogenerate -m "rbac_tables"
```

If autogenerate doesn't pick up raw SQL tables, create manually:

```bash
DB_ENV=online alembic revision -m "rbac_tables"
```

**Step 2: Write migration content**

Replace the generated file body with:

```python
"""rbac_tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'  # adjust to actual last revision
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'permission_points',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.String(255)),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_table(
        'permission_groups',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.String(255)),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_table(
        'group_permission_points',
        sa.Column('group_id', sa.Integer, sa.ForeignKey('permission_groups.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('point_id', sa.Integer, sa.ForeignKey('permission_points.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(50), nullable=False, unique=True),
        sa.Column('description', sa.String(255)),
        sa.Column('created_at', sa.DateTime, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_table(
        'role_permission_groups',
        sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('group_id', sa.Integer, sa.ForeignKey('permission_groups.id', ondelete='CASCADE'), primary_key=True),
    )
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Integer, sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role_id', sa.Integer, sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    )


def downgrade():
    op.drop_table('user_roles')
    op.drop_table('role_permission_groups')
    op.drop_table('group_permission_points')
    op.drop_table('roles')
    op.drop_table('permission_groups')
    op.drop_table('permission_points')
```

**Step 3: Run migration**

```bash
DB_ENV=online alembic upgrade head
```

Expected: 6 tables created without error.

**Step 4: Commit**

```bash
git add alembic/versions/b2c3d4e5f6a7_rbac_tables.py
git commit -m "feat(rbac): add RBAC DB migration (6 tables)"
```

---

### Task 1: ORM Models for RBAC tables

**Files:**
- Create: `api/models/permission.py`
- Modify: `api/models/__init__.py` (import new models)

**Step 1: Create `api/models/permission.py`**

```python
# -*- coding: utf-8 -*-
"""
RBAC ORM models: PermissionPoint, PermissionGroup, Role, UserRole.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from api.models.base import Base

# Association tables (no ORM class needed)
group_permission_points = Table(
    'group_permission_points', Base.metadata,
    Column('group_id', Integer, ForeignKey('permission_groups.id', ondelete='CASCADE'), primary_key=True),
    Column('point_id', Integer, ForeignKey('permission_points.id', ondelete='CASCADE'), primary_key=True),
)

role_permission_groups = Table(
    'role_permission_groups', Base.metadata,
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('group_id', Integer, ForeignKey('permission_groups.id', ondelete='CASCADE'), primary_key=True),
)

user_roles = Table(
    'user_roles', Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
)


class PermissionPoint(Base):
    __tablename__ = 'permission_points'

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(100), nullable=False, unique=True)
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    groups = relationship('PermissionGroup', secondary=group_permission_points, back_populates='points')


class PermissionGroup(Base):
    __tablename__ = 'permission_groups'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    points = relationship('PermissionPoint', secondary=group_permission_points, back_populates='groups')
    roles = relationship('Role', secondary=role_permission_groups, back_populates='groups')


class Role(Base):
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    groups = relationship('PermissionGroup', secondary=role_permission_groups, back_populates='roles')
```

**Step 2: Check `api/models/base.py` exists**

If no separate `base.py`, check `api/models/user.py` for how `Base` is defined and import from there.

**Step 3: Commit**

```bash
git add api/models/permission.py api/models/__init__.py
git commit -m "feat(rbac): add ORM models for permission tables"
```

---

### Task 2: PermissionChecker — core dependency

**Files:**
- Create: `api/core/permissions.py`
- Create: `tests/unit/api/core/__init__.py`
- Create: `tests/unit/api/core/test_permissions.py`

**Step 1: Write failing tests**

```python
# -*- coding: utf-8 -*-
"""Tests for PermissionChecker."""
import pytest
from unittest.mock import AsyncMock, MagicMock


def _make_user(tier='free', permissions=None):
    """Helper: make a mock user with a cached permissions set."""
    user = MagicMock()
    user.id = 1
    user.tier = tier
    user._cached_permissions = permissions or set()
    return user


def test_has_permission_direct_match():
    from api.core.permissions import has_permission
    user = _make_user(permissions={'market.factors', 'market.kline'})
    assert has_permission(user, 'market.factors') is True
    assert has_permission(user, 'market.kline') is True
    assert has_permission(user, 'research.valuation') is False


def test_has_permission_wildcard():
    from api.core.permissions import has_permission
    user = _make_user(permissions={'admin.*'})
    assert has_permission(user, 'admin.users.list') is True
    assert has_permission(user, 'market.kline') is False


def test_has_permission_admin_star_grants_all():
    """admin.* should grant literally any permission."""
    from api.core.permissions import has_permission
    user = _make_user(permissions={'admin.*'})
    # admin.* is special — grants ALL
    assert has_permission(user, 'anything.at.all') is True


def test_permission_codes_defined():
    """All expected permission codes must be importable."""
    from api.core.permissions import Perm
    assert hasattr(Perm, 'MARKET_KLINE')
    assert hasattr(Perm, 'MARKET_FACTORS')
    assert hasattr(Perm, 'RESEARCH_VALUATION')
    assert hasattr(Perm, 'AI_RAG_QUERY')
    assert hasattr(Perm, 'ADMIN_USERS_LIST')


def test_free_tier_default_permissions():
    """FREE_PERMISSIONS must not include pro-only points."""
    from api.core.permissions import FREE_PERMISSIONS, PRO_PERMISSIONS
    assert 'market.kline' in FREE_PERMISSIONS
    assert 'market.factors' not in FREE_PERMISSIONS
    assert 'market.factors' in PRO_PERMISSIONS
    assert 'research.valuation' in PRO_PERMISSIONS
```

**Step 2: Run to confirm failure**

```bash
PYTHONPATH=. pytest tests/unit/api/core/test_permissions.py -v 2>&1 | head -15
```

**Step 3: Create `api/core/permissions.py`**

```python
# -*- coding: utf-8 -*-
"""
RBAC Permission Checker for myTrader API.

Usage in endpoints:
    from api.core.permissions import require_permission, Perm

    @router.get('/factors')
    async def get_factors(
        _: None = Depends(require_permission(Perm.MARKET_FACTORS)),
        current_user: User = Depends(get_current_user),
    ):
        ...
"""
import logging
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status

logger = logging.getLogger('myTrader.api')


# ============================================================
# Permission Point Codes (single source of truth)
# ============================================================
class Perm:
    # Market data
    MARKET_KLINE        = 'market.kline'
    MARKET_SEARCH       = 'market.search'
    MARKET_LATEST_DATE  = 'market.latest_date'
    MARKET_INDICATORS   = 'market.indicators'
    MARKET_FACTORS      = 'market.factors'
    MARKET_RPS          = 'market.rps'

    # Portfolio
    PORTFOLIO_SUMMARY   = 'portfolio.summary'
    PORTFOLIO_HISTORY   = 'portfolio.history'

    # Research (五截面)
    RESEARCH_FUNDAMENTAL = 'research.fundamental'
    RESEARCH_VALUATION   = 'research.valuation'
    RESEARCH_SENTIMENT   = 'research.sentiment'
    RESEARCH_COMPOSITE   = 'research.composite'
    RESEARCH_WATCHLIST   = 'research.watchlist'

    # AI / RAG
    AI_RAG_QUERY         = 'ai.rag.query'
    AI_RAG_REPORT        = 'ai.rag.report'
    AI_ANALYSIS_TECH     = 'ai.analysis.technical'
    AI_ANALYSIS_FUND     = 'ai.analysis.fundamental'

    # Strategy
    STRATEGY_LIST        = 'strategy.list'
    STRATEGY_BACKTEST    = 'strategy.backtest'

    # Admin
    ADMIN_USERS_LIST     = 'admin.users.list'
    ADMIN_USERS_EDIT     = 'admin.users.edit'
    ADMIN_LOGS           = 'admin.logs'
    ADMIN_ALL            = 'admin.*'


# ============================================================
# Default permission sets by tier (used when DB is unavailable)
# ============================================================
FREE_PERMISSIONS: frozenset[str] = frozenset({
    Perm.MARKET_KLINE,
    Perm.MARKET_SEARCH,
    Perm.MARKET_LATEST_DATE,
    Perm.PORTFOLIO_SUMMARY,
    Perm.PORTFOLIO_HISTORY,
    Perm.STRATEGY_LIST,
})

PRO_PERMISSIONS: frozenset[str] = frozenset(FREE_PERMISSIONS | {
    Perm.MARKET_INDICATORS,
    Perm.MARKET_FACTORS,
    Perm.MARKET_RPS,
    Perm.RESEARCH_FUNDAMENTAL,
    Perm.RESEARCH_VALUATION,
    Perm.RESEARCH_SENTIMENT,
    Perm.RESEARCH_COMPOSITE,
    Perm.RESEARCH_WATCHLIST,
    Perm.AI_RAG_QUERY,
    Perm.AI_RAG_REPORT,
    Perm.AI_ANALYSIS_TECH,
    Perm.AI_ANALYSIS_FUND,
    Perm.STRATEGY_BACKTEST,
})

_TIER_DEFAULTS: dict[str, frozenset[str]] = {
    'free':  FREE_PERMISSIONS,
    'pro':   PRO_PERMISSIONS,
    'admin': frozenset({'admin.*'}),
}


# ============================================================
# Core check — does a user (with a cached permissions set) have a permission?
# ============================================================
def has_permission(user, point: str) -> bool:
    """
    Return True if user's cached permission set contains `point`.

    Wildcard rule:
    - 'admin.*' in user permissions -> grants ALL permissions
    - 'market.*' in user permissions -> grants any 'market.xxx'
    """
    perms: set[str] = getattr(user, '_cached_permissions', set())

    # admin.* is a superuser grant
    if 'admin.*' in perms:
        return True

    # Direct match
    if point in perms:
        return True

    # Prefix wildcard: 'market.*' covers 'market.kline'
    prefix = point.rsplit('.', 1)[0] + '.*'
    if prefix in perms:
        return True

    return False


# ============================================================
# Async loader — fetch user's permissions from DB or fall back to tier defaults
# ============================================================
async def load_user_permissions(user, db) -> set[str]:
    """
    Load permission points for user from DB (via role graph).
    Falls back to tier-based defaults if DB is unavailable or user has no roles.
    """
    try:
        from sqlalchemy import text
        result = await db.execute(
            text("""
                SELECT DISTINCT pp.code
                FROM user_roles ur
                JOIN role_permission_groups rpg ON rpg.role_id = ur.role_id
                JOIN group_permission_points gpp ON gpp.group_id = rpg.group_id
                JOIN permission_points pp ON pp.id = gpp.point_id
                WHERE ur.user_id = :uid
            """),
            {'uid': user.id},
        )
        codes = {row[0] for row in result.fetchall()}
        if codes:
            return codes
    except Exception as e:
        logger.warning('[PERMISSIONS] DB lookup failed, using tier defaults: %s', e)

    # Fall back to tier defaults
    tier = getattr(user, 'tier', 'free')
    return set(_TIER_DEFAULTS.get(tier, FREE_PERMISSIONS))


# ============================================================
# FastAPI dependency factory
# ============================================================
def require_permission(point: str):
    """
    FastAPI dependency factory. Use as:

        @router.get('/factors')
        async def get_factors(
            _: None = Depends(require_permission(Perm.MARKET_FACTORS)),
        ):
    """
    async def _checker(
        current_user=Depends(_get_current_user_lazy()),
        db=Depends(_get_db_lazy()),
    ):
        # Load and cache permissions on the user object for this request
        if not hasattr(current_user, '_cached_permissions'):
            current_user._cached_permissions = await load_user_permissions(current_user, db)

        if not has_permission(current_user, point):
            logger.warning(
                '[PERMISSION_DENIED] user=%s point=%s tier=%s',
                current_user.id, point, current_user.tier,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Permission required: {point}',
            )

    return _checker


def _get_current_user_lazy():
    """Lazy import to avoid circular dependency."""
    from api.middleware.auth import get_current_user
    return get_current_user


def _get_db_lazy():
    """Lazy import to avoid circular dependency."""
    from api.dependencies import get_db
    return get_db
```

**Step 4: Run tests**

```bash
PYTHONPATH=. pytest tests/unit/api/core/test_permissions.py -v
```

Expected: 5 passed.

**Step 5: Commit**

```bash
git add api/core/permissions.py tests/unit/api/core/
git commit -m "feat(rbac): add PermissionChecker with tier fallback and wildcard support"
```

---

### Task 3: Seed script — default roles, groups, permission points

**Files:**
- Create: `scripts/seed_permissions.py`

**Step 1: Create `scripts/seed_permissions.py`**

```python
# -*- coding: utf-8 -*-
"""
Seed default RBAC data:
  - Roles: free_user, pro_user, admin
  - PermissionGroups: market_basic, market_advanced, portfolio_basic,
                      research_all, ai_analysis, strategy_basic, strategy_pro, admin_all
  - PermissionPoints: all Perm.* codes
  - Links role -> groups -> points

Run: DB_ENV=online python scripts/seed_permissions.py
"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config.db import get_connection
from api.core.permissions import Perm

POINTS = [
    (Perm.MARKET_KLINE,       'K-line data access'),
    (Perm.MARKET_SEARCH,      'Stock search'),
    (Perm.MARKET_LATEST_DATE, 'Latest trading date'),
    (Perm.MARKET_INDICATORS,  'Technical indicators (MA/MACD/RSI...)'),
    (Perm.MARKET_FACTORS,     'Quantitative factors'),
    (Perm.MARKET_RPS,         'Relative price strength'),
    (Perm.PORTFOLIO_SUMMARY,  'Portfolio summary'),
    (Perm.PORTFOLIO_HISTORY,  'Portfolio history'),
    (Perm.RESEARCH_FUNDAMENTAL, 'Fundamental snapshot'),
    (Perm.RESEARCH_VALUATION,   'Valuation methods'),
    (Perm.RESEARCH_SENTIMENT,   'Sentiment scoring'),
    (Perm.RESEARCH_COMPOSITE,   'Composite five-section score'),
    (Perm.RESEARCH_WATCHLIST,   'Watchlist management'),
    (Perm.AI_RAG_QUERY,     'AI RAG query'),
    (Perm.AI_RAG_REPORT,    'AI research report generation'),
    (Perm.AI_ANALYSIS_TECH, 'AI technical analysis'),
    (Perm.AI_ANALYSIS_FUND, 'AI fundamental analysis'),
    (Perm.STRATEGY_LIST,    'List strategies'),
    (Perm.STRATEGY_BACKTEST,'Run backtests'),
    (Perm.ADMIN_USERS_LIST, 'List users'),
    (Perm.ADMIN_USERS_EDIT, 'Edit users'),
    (Perm.ADMIN_LOGS,       'View server logs'),
    (Perm.ADMIN_ALL,        'Admin wildcard - all permissions'),
]

GROUPS = {
    'market_basic':     [Perm.MARKET_KLINE, Perm.MARKET_SEARCH, Perm.MARKET_LATEST_DATE],
    'market_advanced':  [Perm.MARKET_INDICATORS, Perm.MARKET_FACTORS, Perm.MARKET_RPS],
    'portfolio_basic':  [Perm.PORTFOLIO_SUMMARY, Perm.PORTFOLIO_HISTORY],
    'research_all':     [Perm.RESEARCH_FUNDAMENTAL, Perm.RESEARCH_VALUATION,
                         Perm.RESEARCH_SENTIMENT, Perm.RESEARCH_COMPOSITE, Perm.RESEARCH_WATCHLIST],
    'ai_analysis':      [Perm.AI_RAG_QUERY, Perm.AI_RAG_REPORT,
                         Perm.AI_ANALYSIS_TECH, Perm.AI_ANALYSIS_FUND],
    'strategy_basic':   [Perm.STRATEGY_LIST],
    'strategy_pro':     [Perm.STRATEGY_LIST, Perm.STRATEGY_BACKTEST],
    'admin_all':        [Perm.ADMIN_USERS_LIST, Perm.ADMIN_USERS_EDIT,
                         Perm.ADMIN_LOGS, Perm.ADMIN_ALL],
}

ROLES = {
    'free_user': {
        'description': 'Default free tier user',
        'groups': ['market_basic', 'portfolio_basic', 'strategy_basic'],
    },
    'pro_user': {
        'description': 'Pro subscription user',
        'groups': ['market_basic', 'market_advanced', 'portfolio_basic',
                   'research_all', 'ai_analysis', 'strategy_pro'],
    },
    'admin': {
        'description': 'System administrator',
        'groups': ['market_basic', 'market_advanced', 'portfolio_basic',
                   'research_all', 'ai_analysis', 'strategy_pro', 'admin_all'],
    },
}


def seed():
    conn = get_connection(env='online')
    cursor = conn.cursor()

    print('[SEED] Inserting permission_points...')
    for code, desc in POINTS:
        cursor.execute(
            'INSERT INTO permission_points (code, description) VALUES (%s, %s) '
            'ON DUPLICATE KEY UPDATE description=VALUES(description)',
            (code, desc),
        )

    print('[SEED] Inserting permission_groups...')
    for name in GROUPS:
        cursor.execute(
            'INSERT INTO permission_groups (name) VALUES (%s) '
            'ON DUPLICATE KEY UPDATE name=name',
            (name,),
        )

    print('[SEED] Linking groups -> points...')
    for group_name, point_codes in GROUPS.items():
        cursor.execute('SELECT id FROM permission_groups WHERE name=%s', (group_name,))
        gid = cursor.fetchone()[0]
        for code in point_codes:
            cursor.execute('SELECT id FROM permission_points WHERE code=%s', (code,))
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    'INSERT IGNORE INTO group_permission_points (group_id, point_id) VALUES (%s, %s)',
                    (gid, row[0]),
                )

    print('[SEED] Inserting roles...')
    for role_name, role_data in ROLES.items():
        cursor.execute(
            'INSERT INTO roles (name, description) VALUES (%s, %s) '
            'ON DUPLICATE KEY UPDATE description=VALUES(description)',
            (role_name, role_data['description']),
        )

    print('[SEED] Linking roles -> groups...')
    for role_name, role_data in ROLES.items():
        cursor.execute('SELECT id FROM roles WHERE name=%s', (role_name,))
        rid = cursor.fetchone()[0]
        for group_name in role_data['groups']:
            cursor.execute('SELECT id FROM permission_groups WHERE name=%s', (group_name,))
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    'INSERT IGNORE INTO role_permission_groups (role_id, group_id) VALUES (%s, %s)',
                    (rid, row[0]),
                )

    conn.commit()
    cursor.close()
    conn.close()
    print('[SEED] Done. Default roles seeded: free_user, pro_user, admin')


if __name__ == '__main__':
    seed()
```

**Step 2: Run seed**

```bash
DB_ENV=online python scripts/seed_permissions.py
```

Expected:
```
[SEED] Inserting permission_points...
[SEED] Inserting permission_groups...
[SEED] Linking groups -> points...
[SEED] Inserting roles...
[SEED] Linking roles -> groups...
[SEED] Done. Default roles seeded: free_user, pro_user, admin
```

**Step 3: Commit**

```bash
git add scripts/seed_permissions.py
git commit -m "feat(rbac): add seed script for default roles and permission points"
```

---

### Task 4: Auto-assign role at registration + tier upgrade

**Files:**
- Modify: `api/routers/auth.py` (assign `free_user` role on register)
- Modify: `api/routers/subscription.py` (upgrade role to `pro_user` on plan upgrade)

**Step 1: Add helper in `api/core/permissions.py`**

Append to `api/core/permissions.py`:

```python
async def assign_role_to_user(user_id: int, role_name: str, db) -> bool:
    """Add a role to a user. Idempotent (INSERT IGNORE)."""
    try:
        from sqlalchemy import text
        await db.execute(
            text("""
                INSERT IGNORE INTO user_roles (user_id, role_id)
                SELECT :uid, id FROM roles WHERE name = :role
            """),
            {'uid': user_id, 'role': role_name},
        )
        await db.commit()
        return True
    except Exception as e:
        logger.error('[RBAC] assign_role_to_user failed: %s', e)
        return False


async def remove_role_from_user(user_id: int, role_name: str, db) -> bool:
    """Remove a role from a user."""
    try:
        from sqlalchemy import text
        await db.execute(
            text("""
                DELETE ur FROM user_roles ur
                JOIN roles r ON r.id = ur.role_id
                WHERE ur.user_id = :uid AND r.name = :role
            """),
            {'uid': user_id, 'role': role_name},
        )
        await db.commit()
        return True
    except Exception as e:
        logger.error('[RBAC] remove_role_from_user failed: %s', e)
        return False
```

**Step 2: Modify `api/routers/auth.py` — assign `free_user` after register**

In the register endpoint, after the user is created and committed, add:

```python
from api.core.permissions import assign_role_to_user
# ...
await assign_role_to_user(new_user.id, 'free_user', db)
```

**Step 3: Modify `api/routers/subscription.py` — role upgrade**

In the `upgrade_subscription` endpoint, after `db.commit()` (after updating user tier), add:

```python
from api.core.permissions import assign_role_to_user, remove_role_from_user
# ...
await remove_role_from_user(current_user.id, 'free_user', db)
await assign_role_to_user(current_user.id, 'pro_user', db)
```

**Step 4: Commit**

```bash
git add api/routers/auth.py api/routers/subscription.py api/core/permissions.py
git commit -m "feat(rbac): assign roles at registration and subscription upgrade"
```

---

### Task 5: Gate pro endpoints with require_permission

**Files:**
- Modify: `api/routers/market.py`
- Modify: `api/routers/research.py`
- Modify: `api/routers/analysis.py`

**Step 1: Gate `market.py` advanced endpoints**

For each pro-only endpoint (factors, indicators, rps), add the dependency:

```python
from api.core.permissions import require_permission, Perm

@router.get('/factors')
async def get_factors(
    _: None = Depends(require_permission(Perm.MARKET_FACTORS)),
    current_user: User = Depends(get_current_user),
    ...
):
```

Apply to:
- `/api/market/factors` → `Perm.MARKET_FACTORS`
- `/api/market/indicators` → `Perm.MARKET_INDICATORS`
- `/api/market/rps` → `Perm.MARKET_RPS`

Free endpoints (kline, search, latest-date) get no gate.

**Step 2: Gate all `research.py` endpoints**

```python
from api.core.permissions import require_permission, Perm

# Map endpoint -> permission
# GET  /fundamental/{code}          -> RESEARCH_FUNDAMENTAL
# POST /fundamental/{code}/refresh  -> RESEARCH_FUNDAMENTAL
# GET  /valuation/{code}            -> RESEARCH_VALUATION
# GET  /sentiment/{code}/events     -> RESEARCH_SENTIMENT
# POST /sentiment/events            -> RESEARCH_SENTIMENT
# PUT  /sentiment/events/{id}/verify -> RESEARCH_SENTIMENT
# GET  /composite/{code}            -> RESEARCH_COMPOSITE
# POST /composite/{code}/compute    -> RESEARCH_COMPOSITE
# GET  /watchlist                   -> RESEARCH_WATCHLIST
# POST /watchlist                   -> RESEARCH_WATCHLIST
# PUT  /watchlist/{code}/tier       -> RESEARCH_WATCHLIST
# PUT  /watchlist/{code}/thesis     -> RESEARCH_WATCHLIST
# DELETE /watchlist/{code}          -> RESEARCH_WATCHLIST
```

Add `_: None = Depends(require_permission(Perm.RESEARCH_XXX))` to each.

**Step 3: Gate `analysis.py` AI endpoints**

```python
# GET /api/analysis/technical    -> Perm.AI_ANALYSIS_TECH
# GET /api/analysis/fundamental  -> Perm.AI_ANALYSIS_FUND
```

**Step 4: Gate `rag.py` endpoints**

```python
# POST /api/rag/query         -> Perm.AI_RAG_QUERY
# POST /api/rag/report/generate -> Perm.AI_RAG_REPORT
```

**Step 5: Commit**

```bash
git add api/routers/market.py api/routers/research.py \
        api/routers/analysis.py api/routers/rag.py
git commit -m "feat(rbac): gate pro and AI endpoints with require_permission"
```

---

### Task 6: Admin API for role/permission management

**Files:**
- Create: `api/routers/permissions.py`
- Modify: `api/main.py` (include router)

**Step 1: Create `api/routers/permissions.py`**

```python
# -*- coding: utf-8 -*-
"""
Permission management API (admin only).

GET  /api/permissions/roles           - list roles
GET  /api/permissions/roles/{name}    - role detail with permission groups
GET  /api/permissions/points          - list all permission points
POST /api/permissions/users/{id}/roles - assign role to user
DELETE /api/permissions/users/{id}/roles/{role} - remove role from user
GET  /api/permissions/users/{id}/roles - list user's roles and effective permissions
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.core.permissions import (
    require_permission, Perm,
    assign_role_to_user, remove_role_from_user, load_user_permissions,
)

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/permissions', tags=['permissions'])


@router.get('/roles')
async def list_roles(
    _: None = Depends(require_permission(Perm.ADMIN_USERS_LIST)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text('SELECT id, name, description FROM roles ORDER BY id'))
    rows = [dict(r._mapping) for r in result.fetchall()]
    return {'roles': rows}


@router.get('/points')
async def list_permission_points(
    _: None = Depends(require_permission(Perm.ADMIN_USERS_LIST)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(text('SELECT id, code, description FROM permission_points ORDER BY code'))
    rows = [dict(r._mapping) for r in result.fetchall()]
    return {'points': rows}


@router.get('/users/{user_id}/roles')
async def get_user_roles(
    user_id: int,
    _: None = Depends(require_permission(Perm.ADMIN_USERS_LIST)),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT r.name, r.description
            FROM user_roles ur
            JOIN roles r ON r.id = ur.role_id
            WHERE ur.user_id = :uid
        """),
        {'uid': user_id},
    )
    roles = [dict(r._mapping) for r in result.fetchall()]

    # Load effective permissions
    mock_user = type('U', (), {'id': user_id, 'tier': 'free'})()
    perms = await load_user_permissions(mock_user, db)

    return {
        'user_id': user_id,
        'roles': roles,
        'effective_permissions': sorted(perms),
    }


@router.post('/users/{user_id}/roles')
async def assign_role(
    user_id: int,
    role: str,
    _: None = Depends(require_permission(Perm.ADMIN_USERS_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    ok = await assign_role_to_user(user_id, role, db)
    if not ok:
        raise HTTPException(status_code=500, detail='Failed to assign role')
    return {'message': f'Role {role!r} assigned to user {user_id}'}


@router.delete('/users/{user_id}/roles/{role}')
async def remove_role(
    user_id: int,
    role: str,
    _: None = Depends(require_permission(Perm.ADMIN_USERS_EDIT)),
    db: AsyncSession = Depends(get_db),
):
    ok = await remove_role_from_user(user_id, role, db)
    if not ok:
        raise HTTPException(status_code=500, detail='Failed to remove role')
    return {'message': f'Role {role!r} removed from user {user_id}'}
```

**Step 2: Register in `api/main.py`**

```python
from api.routers import ..., permissions

app.include_router(permissions.router)
```

**Step 3: Commit**

```bash
git add api/routers/permissions.py api/main.py
git commit -m "feat(rbac): add permission management API endpoints"
```

---

### Task 7: Integration smoke test

**Step 1: Restart API**

```bash
PYTHONPATH=. LOG_LEVEL=DEBUG DB_ENV=online uvicorn api.main:app --port 8001 --reload
```

**Step 2: Run seed (if DB is accessible)**

```bash
DB_ENV=online python scripts/seed_permissions.py
```

**Step 3: Test permission denial on free endpoint**

```bash
# Free user trying to access pro endpoint (403 expected)
curl "http://localhost:8001/api/market/factors?code=600519" \
  -H "Authorization: Bearer $FREE_USER_TOKEN"
# Expected: {"detail":"Permission required: market.factors"}

# Pro user same endpoint (200 expected)
curl "http://localhost:8001/api/market/factors?code=600519" \
  -H "Authorization: Bearer $PRO_USER_TOKEN"
```

**Step 4: Commit any cleanup**

```bash
git add .
git commit -m "feat(rbac): complete RBAC system with role assignment and permission gating"
```

---

## File Summary

| File | Action |
|------|--------|
| `alembic/versions/b2c3d4e5f6a7_rbac_tables.py` | Create — 6 RBAC tables |
| `api/models/permission.py` | Create — ORM models |
| `api/core/permissions.py` | Create — Perm codes, has_permission, require_permission, assign/remove role |
| `scripts/seed_permissions.py` | Create — seed default roles/groups/points |
| `api/routers/auth.py` | Modify — assign free_user on register |
| `api/routers/subscription.py` | Modify — swap role on pro upgrade |
| `api/routers/market.py` | Modify — gate factors/indicators/rps |
| `api/routers/research.py` | Modify — gate all 13 endpoints |
| `api/routers/analysis.py` | Modify — gate AI analysis |
| `api/routers/rag.py` | Modify — gate RAG query/report |
| `api/routers/permissions.py` | Create — admin permission CRUD API |
| `api/main.py` | Modify — include permissions router |
| `tests/unit/api/core/test_permissions.py` | Create — 5 tests |

## Permission Quick Reference

| Endpoint | Required Permission | Free? |
|----------|-------------------|-------|
| `GET /api/market/kline` | none (authenticated) | yes |
| `GET /api/market/factors` | `market.factors` | no |
| `GET /api/market/rps` | `market.rps` | no |
| `GET /api/research/valuation/{code}` | `research.valuation` | no |
| `POST /api/research/composite/{code}/compute` | `research.composite` | no |
| `POST /api/rag/query` | `ai.rag.query` | no |
| `POST /api/rag/report/generate` | `ai.rag.report` | no |
| `GET /api/admin/logs` | `admin.logs` | no |
