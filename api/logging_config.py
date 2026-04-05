# -*- coding: utf-8 -*-
"""
Centralized logging configuration for myTrader API.

Usage:
    from api.logging_config import setup_logging
    setup_logging(log_level='INFO', log_dir='logs')

Three output streams:
    logs/app.log    - All myTrader events (level-controlled)
    logs/error.log  - ERROR+ events only
    logs/access.log - One line per HTTP request
"""
import logging
import logging.config
import os
from pathlib import Path


# Log format: timestamp  [LEVEL   ] logger_name:lineno - message
_FMT_VERBOSE = '%(asctime)s [%(levelname)-8s] %(name)s:%(lineno)d - %(message)s'
_FMT_ACCESS  = '%(asctime)s [ACCESS  ] %(message)s'
_DATE_FMT    = '%Y-%m-%d %H:%M:%S'


def _build_config(log_level: str, log_dir: str) -> dict:
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    return {
        'version': 1,
        'disable_existing_loggers': False,

        'formatters': {
            'verbose': {
                'format': _FMT_VERBOSE,
                'datefmt': _DATE_FMT,
            },
            'access': {
                'format': _FMT_ACCESS,
                'datefmt': _DATE_FMT,
            },
        },

        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stdout',
                'formatter': 'verbose',
                'level': log_level,
            },
            'file_app': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(log_dir, 'app.log'),
                'maxBytes': 10 * 1024 * 1024,   # 10 MB
                'backupCount': 5,
                'formatter': 'verbose',
                'encoding': 'utf-8',
                'level': log_level,
            },
            'file_error': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(log_dir, 'error.log'),
                'maxBytes': 10 * 1024 * 1024,
                'backupCount': 3,
                'formatter': 'verbose',
                'encoding': 'utf-8',
                'level': 'ERROR',
            },
            'file_access': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': os.path.join(log_dir, 'access.log'),
                'maxBytes': 50 * 1024 * 1024,  # 50 MB
                'backupCount': 7,
                'formatter': 'access',
                'encoding': 'utf-8',
                'level': 'INFO',
            },
        },

        'loggers': {
            # Application logger -- all API code uses logging.getLogger('myTrader.xxx')
            'myTrader': {
                'handlers': ['console', 'file_app', 'file_error'],
                'level': log_level,
                'propagate': False,
            },
            # HTTP access log -- emitted by AccessLogMiddleware
            'myTrader.access': {
                'handlers': ['console', 'file_access'],
                'level': 'INFO',
                'propagate': False,
            },
            # Silence SQLAlchemy SQL echo unless DEBUG
            'sqlalchemy.engine': {
                'handlers': ['file_app'],
                'level': 'WARNING' if log_level != 'DEBUG' else 'INFO',
                'propagate': False,
            },
            # Uvicorn's own loggers -- keep them going to console
            'uvicorn': {
                'handlers': ['console'],
                'level': 'INFO',
                'propagate': False,
            },
            'uvicorn.access': {
                'handlers': ['console', 'file_access'],
                'level': 'INFO',
                'propagate': False,
            },
        },

        'root': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    }


def setup_logging(log_level: str = 'INFO', log_dir: str = 'logs') -> None:
    """
    Configure logging for the entire application.

    Args:
        log_level: One of DEBUG / INFO / WARNING / ERROR / CRITICAL.
                   Controlled by LOG_LEVEL env var in production.
        log_dir:   Directory to write rotating log files into.
                   Will be created if it does not exist.
    """
    level = log_level.upper()
    if level not in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        level = 'INFO'

    config = _build_config(level, log_dir)
    logging.config.dictConfig(config)
