# -*- coding: utf-8 -*-
"""
WatchlistManager — CRUD for the watchlist table.

Table DDL (reference):
    CREATE TABLE watchlist (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        code           VARCHAR(10) NOT NULL UNIQUE,
        name           VARCHAR(50),
        tier           ENUM('deep','standard','watch') NOT NULL DEFAULT 'watch',
        industry       VARCHAR(50),
        current_thesis VARCHAR(200),
        thesis_updated_at DATE,
        profile_yaml   TEXT,
        is_active      TINYINT(1) NOT NULL DEFAULT 1,
        created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    );
"""

from datetime import date

try:
    from config.db import execute_query
except ImportError:
    execute_query = None

VALID_TIERS = ('deep', 'standard', 'watch')


class WatchlistManager:
    """CRUD manager for the watchlist company pool."""

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def add(
        self,
        code: str,
        name: str | None = None,
        tier: str = 'watch',
        industry: str | None = None,
        thesis: str | None = None,
    ) -> None:
        """INSERT ... ON DUPLICATE KEY UPDATE — re-activates if previously removed.

        Raises ValueError if tier not in VALID_TIERS.
        """
        if tier not in VALID_TIERS:
            raise ValueError(
                f"Invalid tier {tier!r}. Must be one of {VALID_TIERS}."
            )
        sql = """
            INSERT INTO watchlist (code, name, tier, industry, current_thesis, is_active)
            VALUES (%s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                name             = COALESCE(VALUES(name), name),
                tier             = VALUES(tier),
                industry         = COALESCE(VALUES(industry), industry),
                current_thesis   = COALESCE(VALUES(current_thesis), current_thesis),
                is_active        = 1,
                updated_at       = CURRENT_TIMESTAMP
        """
        params = (code, name, tier, industry, thesis)
        execute_query(sql, params)

    def remove(self, code: str) -> None:
        """Soft-delete: set is_active=0."""
        sql = "UPDATE watchlist SET is_active = 0 WHERE code = %s"
        execute_query(sql, (code,))

    def set_tier(self, code: str, tier: str) -> None:
        """Update tier for a stock.

        Raises ValueError if tier not in VALID_TIERS.
        """
        if tier not in VALID_TIERS:
            raise ValueError(
                f"Invalid tier {tier!r}. Must be one of {VALID_TIERS}."
            )
        sql = "UPDATE watchlist SET tier = %s WHERE code = %s"
        execute_query(sql, (tier, code))

    def save_profile(self, code: str, yaml_str: str) -> None:
        """Store YAML profile blob for a stock."""
        sql = "UPDATE watchlist SET profile_yaml = %s WHERE code = %s"
        execute_query(sql, (yaml_str, code))

    def update_thesis(self, code: str, thesis: str) -> None:
        """Update investment thesis, truncated to 200 chars."""
        truncated = thesis[:200]
        today = str(date.today())
        sql = """
            UPDATE watchlist
            SET current_thesis = %s, thesis_updated_at = %s
            WHERE code = %s
        """
        execute_query(sql, (truncated, today, code))

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, code: str) -> dict | None:
        """Return the watchlist row for a given code, or None."""
        sql = "SELECT * FROM watchlist WHERE code = %s"
        rows = execute_query(sql, (code,))
        if rows:
            return rows[0]
        return None

    def list_active(self, tier: str | None = None) -> list[dict]:
        """Return all active watchlist entries, optionally filtered by tier."""
        if tier is not None:
            sql = (
                "SELECT * FROM watchlist "
                "WHERE is_active = 1 AND tier = %s "
                "ORDER BY tier, code"
            )
            rows = execute_query(sql, (tier,))
        else:
            sql = (
                "SELECT * FROM watchlist "
                "WHERE is_active = 1 "
                "ORDER BY tier, code"
            )
            rows = execute_query(sql)
        return rows if rows is not None else []
