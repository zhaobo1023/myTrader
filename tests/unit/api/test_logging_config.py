# -*- coding: utf-8 -*-
import logging
import os
import tempfile
import pytest


def test_setup_logging_creates_mytrader_logger():
    """setup_logging must attach at least one handler to myTrader logger."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from api.logging_config import setup_logging
        setup_logging(log_level='DEBUG', log_dir=tmpdir)
        logger = logging.getLogger('myTrader')
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) >= 1


def test_setup_logging_creates_log_files():
    """setup_logging must create app.log and error.log under log_dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from api.logging_config import setup_logging
        setup_logging(log_level='INFO', log_dir=tmpdir)
        logger = logging.getLogger('myTrader.api')
        logger.info('test message')
        assert os.path.exists(os.path.join(tmpdir, 'app.log'))
        assert os.path.exists(os.path.join(tmpdir, 'error.log'))


def test_setup_logging_respects_level():
    """DEBUG messages must reach the logger when level=DEBUG."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from api.logging_config import setup_logging
        setup_logging(log_level='DEBUG', log_dir=tmpdir)
        logger = logging.getLogger('myTrader.test_level')
        logger.debug('debug-marker-xyz')
        with open(os.path.join(tmpdir, 'app.log')) as f:
            content = f.read()
        assert 'debug-marker-xyz' in content


def test_setup_logging_error_goes_to_error_log():
    """ERROR messages must appear in error.log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from api.logging_config import setup_logging
        setup_logging(log_level='INFO', log_dir=tmpdir)
        logger = logging.getLogger('myTrader.test_error')
        logger.error('error-marker-abc')
        with open(os.path.join(tmpdir, 'error.log')) as f:
            content = f.read()
        assert 'error-marker-abc' in content


def test_setup_logging_idempotent():
    """Calling setup_logging twice must not duplicate handlers unboundedly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from api.logging_config import setup_logging
        setup_logging(log_level='INFO', log_dir=tmpdir)
        setup_logging(log_level='INFO', log_dir=tmpdir)
        logger = logging.getLogger('myTrader')
        # dictConfig replaces handlers each call -- should not grow unbounded
        assert len(logger.handlers) <= 3  # console + file_app + file_error
