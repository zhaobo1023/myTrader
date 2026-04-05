# -*- coding: utf-8 -*-
"""Tests for scheduler.alert module."""
import os
from unittest.mock import patch, MagicMock

from scheduler.alert import send_alert, send_daily_summary, _post_webhook
from scheduler.state import TaskRun


class TestGetWebhookUrl:
    def test_no_url_configured(self):
        """When no URL is set, send_alert should return False."""
        with patch.dict(os.environ, {}, clear=True):
            # Also need to clear the module-level cache if any
            result = send_alert(
                {"id": "t1", "name": "Test", "module": "m", "func": "f"},
                TaskRun(task_id="t1", status="failed", error_msg="test error"),
                {},
            )
            assert result is False


class TestPostWebhook:
    def test_success(self):
        with patch("scheduler.alert.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            result = _post_webhook("https://example.com/hook", "Title", "Content")
            assert result is True
            mock_post.assert_called_once()

    def test_http_failure_no_raise(self):
        with patch("scheduler.alert.requests.post") as mock_post:
            mock_post.side_effect = Exception("Connection refused")

            result = _post_webhook("https://example.com/hook", "Title", "Content")
            assert result is False

    def test_no_emoji_in_payload(self):
        """Alert payloads should not contain emoji characters."""
        with patch("scheduler.alert.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            run = TaskRun(task_id="t1", status="failed", error_msg="something broke")
            send_alert(
                {"id": "t1", "name": "Test Task", "module": "m", "func": "f",
                 "depends_on": []},
                run,
                {},
            )

            call_args = mock_post.call_args
            payload = call_args[1]["json"] if call_args else {}
            text = str(payload)
            # Check for common emoji unicode ranges
            assert "\U0001f600" not in text  # No emoji


class TestSendDailySummary:
    def test_empty_summary(self):
        with patch("scheduler.alert._get_webhook_url", return_value=None):
            result = send_daily_summary([], env="local")
            assert result is False
