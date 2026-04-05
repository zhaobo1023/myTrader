# -*- coding: utf-8 -*-
"""
CRUD operations for the sentiment_events table.
"""
import logging

try:
    from config.db import execute_query
except ImportError:
    execute_query = None

logger = logging.getLogger(__name__)

VALID_DIRECTIONS = ('positive', 'negative', 'neutral')
VALID_MAGNITUDES = ('high', 'medium', 'low')
VALID_CATEGORIES = ('capital', 'earnings', 'policy', 'geopolitical',
                    'industry', 'technical', 'shareholder')


class SentimentEventTracker:
    """CRUD interface for sentiment_events table."""

    def create(self, code, event_date, event_text, direction,
               magnitude, category, source=None):
        """Validate inputs, INSERT into sentiment_events, return new id.

        Parameters
        ----------
        code : str
            Stock code (e.g. '300750').
        event_date : str
            Date string in YYYY-MM-DD format.
        event_text : str
            Description of the event (truncated to 300 chars).
        direction : str
            One of VALID_DIRECTIONS.
        magnitude : str
            One of VALID_MAGNITUDES.
        category : str
            One of VALID_CATEGORIES.
        source : str, optional
            Source of the event information.

        Returns
        -------
        int or None
            The new record id on success, None on failure.
        """
        if direction not in VALID_DIRECTIONS:
            raise ValueError(
                "Invalid direction '%s'. Must be one of: %s"
                % (direction, VALID_DIRECTIONS)
            )
        if magnitude not in VALID_MAGNITUDES:
            raise ValueError(
                "Invalid magnitude '%s'. Must be one of: %s"
                % (magnitude, VALID_MAGNITUDES)
            )
        if category not in VALID_CATEGORIES:
            raise ValueError(
                "Invalid category '%s'. Must be one of: %s"
                % (category, VALID_CATEGORIES)
            )

        event_text = (event_text or '')[:300]

        insert_sql = """
            INSERT INTO sentiment_events
                (code, event_date, event_text, direction, magnitude, category, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        select_sql = "SELECT LAST_INSERT_ID() AS id"

        try:
            execute_query(insert_sql, (code, event_date, event_text,
                                       direction, magnitude, category, source))
            rows = execute_query(select_sql)
            if rows:
                return rows[0]['id']
            return None
        except Exception as e:
            logger.error("create failed: %s", e)
            return None

    def list_recent(self, code: str, days: int = 30) -> list:
        """SELECT events for code in last N days, ORDER BY event_date DESC.

        Parameters
        ----------
        code : str
            Stock code to query.
        days : int
            Number of calendar days to look back (default 30).

        Returns
        -------
        list[dict]
            List of row dicts, empty list on failure or no data.
        """
        sql = """
            SELECT id, code, event_date, event_text, direction,
                   magnitude, category, is_verified, verified_result, source
            FROM sentiment_events
            WHERE code = %s
              AND event_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
            ORDER BY event_date DESC
        """
        try:
            rows = execute_query(sql, (code, days))
            return rows if rows else []
        except Exception as e:
            logger.error("list_recent failed: %s", e)
            return []

    def verify(self, event_id: int, result: str) -> None:
        """Mark an event as verified and record the outcome.

        Parameters
        ----------
        event_id : int
            Primary key of the event to update.
        result : str
            Human-readable verification result.
        """
        sql = """
            UPDATE sentiment_events
            SET is_verified = 1, verified_result = %s
            WHERE id = %s
        """
        try:
            execute_query(sql, (result, event_id))
        except Exception as e:
            logger.error("verify failed for event_id=%s: %s", event_id, e)
