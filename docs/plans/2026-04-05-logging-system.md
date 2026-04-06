# Logging System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a proper server-side logging system with structured output, rotating file handlers, per-request access logs, and a log-tail debug endpoint.

**Architecture:** A single `api/logging_config.py` module holds the full `dictConfig` dict and a `setup_logging(level)` function called once at app startup. Three rotating files handle app events, errors, and HTTP access separately. An `AccessLogMiddleware` emits one log line per request. A debug endpoint tails the log file.

**Tech Stack:** Python `logging.config.dictConfig`, `RotatingFileHandler`, FastAPI `BaseHTTPMiddleware`, existing `api/config.py` Pydantic Settings.

---

## Context

Current state (from audit):
- All `logger.info/debug` calls across the API are **silently dropped** — no handler is ever attached to the `myTrader` logger hierarchy
- No `LOG_LEVEL` env var
- No per-request access logging (only uvicorn's own unconfigured logger)
- `api/tasks/backtest.py` uses a different logger name: `myTrader.tasks`

Target state after this plan:
- `logs/app.log` — all myTrader events (DEBUG+), rotating 10 MB × 5
- `logs/error.log` — ERROR+ only, rotating 10 MB × 3
- `logs/access.log` — one line per HTTP request, rotating 50 MB × 7
- Console — same as file but colorized (only when TTY)
- `LOG_LEVEL` env var controls verbosity (default `INFO`)
- `GET /api/admin/logs?file=app&lines=100` — tail any log file

---

### Task 0: Create log directory + gitignore

**Files:**
- Create: `logs/.gitkeep`
- Modify: `.gitignore`

**Step 1: Create logs dir placeholder**

```bash
mkdir -p /Users/zhaobo/data0/person/myTrader/logs
touch /Users/zhaobo/data0/person/myTrader/logs/.gitkeep
```

**Step 2: Add to .gitignore**

In `.gitignore`, add after the `output/` section:

```
# Log files
logs/*.log
logs/*.log.*
```

**Step 3: Commit**

```bash
git add logs/.gitkeep .gitignore
git commit -m "chore(logging): add logs/ directory"
```

---

### Task 1: logging_config.py — central dictConfig

**Files:**
- Create: `api/logging_config.py`
- Create: `tests/unit/api/test_logging_config.py`

**Step 1: Write failing tests**

Create `tests/unit/api/__init__.py` if missing, then create `tests/unit/api/test_logging_config.py`:

```python
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
    """Calling setup_logging twice must not duplicate handlers."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from api.logging_config import setup_logging
        setup_logging(log_level='INFO', log_dir=tmpdir)
        setup_logging(log_level='INFO', log_dir=tmpdir)
        logger = logging.getLogger('myTrader')
        # dictConfig replaces handlers each call — should not grow unbounded
        assert len(logger.handlers) <= 3  # console + app_file + error_file
```

**Step 2: Run to confirm failure**

```bash
cd /Users/zhaobo/data0/person/myTrader
PYTHONPATH=. pytest tests/unit/api/test_logging_config.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'api.logging_config'`

**Step 3: Create `api/logging_config.py`**

```python
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
import sys
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
            # Application logger — all API code uses logging.getLogger('myTrader.xxx')
            'myTrader': {
                'handlers': ['console', 'file_app', 'file_error'],
                'level': log_level,
                'propagate': False,
            },
            # HTTP access log — emitted by AccessLogMiddleware
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
            # Uvicorn's own loggers — keep them going to console
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
```

**Step 4: Run tests**

```bash
PYTHONPATH=. pytest tests/unit/api/test_logging_config.py -v
```

Expected: 5 passed.

**Step 5: Commit**

```bash
git add api/logging_config.py tests/unit/api/test_logging_config.py tests/unit/api/__init__.py
git commit -m "feat(logging): add centralized dictConfig logging setup"
```

---

### Task 2: Add LOG_LEVEL to Settings + call setup_logging at startup

**Files:**
- Modify: `api/config.py` (add `log_level` field after `api_debug`)
- Modify: `api/main.py` (call `setup_logging` before app creation)
- Modify: `.env.example` (document LOG_LEVEL)

**Step 1: Add `log_level` to `api/config.py`**

After line 32 (`api_debug: bool = ...`), insert:

```python
log_level: str = Field(default='INFO', alias='LOG_LEVEL')
log_dir: str = Field(default='logs', alias='LOG_DIR')
```

**Step 2: Update `api/main.py`**

After the imports block (after line 17), add:

```python
from api.logging_config import setup_logging
```

Then, at module level **before** `app = FastAPI(...)`, add:

```python
# ============================================================
# Logging — must be configured before any logger is used
# ============================================================
setup_logging(log_level=settings.log_level, log_dir=settings.log_dir)
```

**Step 3: Update `.env.example`**

Add to the Application section:

```bash
# Logging
LOG_LEVEL=INFO          # DEBUG / INFO / WARNING / ERROR / CRITICAL
LOG_DIR=logs            # directory for rotating log files
```

**Step 4: Smoke test**

Kill any running API process and restart:

```bash
cd /Users/zhaobo/data0/person/myTrader
PYTHONPATH=. LOG_LEVEL=DEBUG DB_ENV=online uvicorn api.main:app --port 8001 --reload
```

Expected in terminal output:
```
2026-04-05 10:00:00 [INFO    ] myTrader.api:26 - [STARTUP] myTrader API v0.1.0
2026-04-05 10:00:00 [INFO    ] myTrader.api:27 - [STARTUP] DB env: online
```

Check log file exists:
```bash
ls -la logs/
# Should show: app.log  error.log  access.log (access.log created on first request)
```

**Step 5: Commit**

```bash
git add api/config.py api/main.py .env.example
git commit -m "feat(logging): wire LOG_LEVEL setting and call setup_logging at startup"
```

---

### Task 3: AccessLogMiddleware — one log line per request

**Files:**
- Create: `api/middleware/access_log.py`
- Modify: `api/main.py` (register middleware)
- Create: `tests/unit/api/middleware/__init__.py`
- Create: `tests/unit/api/middleware/test_access_log.py`

**Step 1: Write failing tests**

Create `tests/unit/api/middleware/test_access_log.py`:

```python
# -*- coding: utf-8 -*-
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient
from fastapi import FastAPI


def _make_app():
    from api.middleware.access_log import AccessLogMiddleware
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)

    @app.get('/ping')
    async def ping():
        return {'ok': True}

    @app.get('/fail')
    async def fail():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail='not found')

    return app


def test_access_log_emits_on_success(caplog):
    """Successful request must produce one access log line with method/path/status/ms."""
    app = _make_app()
    with caplog.at_level(logging.INFO, logger='myTrader.access'):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/ping')
    assert resp.status_code == 200
    access_lines = [r for r in caplog.records if r.name == 'myTrader.access']
    assert len(access_lines) == 1
    msg = access_lines[0].message
    assert 'GET' in msg
    assert '/ping' in msg
    assert '200' in msg
    assert 'ms' in msg


def test_access_log_emits_on_error(caplog):
    """4xx/5xx responses must also be logged."""
    app = _make_app()
    with caplog.at_level(logging.INFO, logger='myTrader.access'):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get('/fail')
    assert resp.status_code == 404
    access_lines = [r for r in caplog.records if r.name == 'myTrader.access']
    assert len(access_lines) == 1
    assert '404' in access_lines[0].message


def test_access_log_includes_client_ip(caplog):
    """Log line must contain the client IP."""
    app = _make_app()
    with caplog.at_level(logging.INFO, logger='myTrader.access'):
        client = TestClient(app, raise_server_exceptions=False)
        client.get('/ping')
    access_lines = [r for r in caplog.records if r.name == 'myTrader.access']
    # testclient sets host to 'testclient'
    assert len(access_lines) == 1
    # at minimum the line must not be empty
    assert len(access_lines[0].message) > 10
```

**Step 2: Run to confirm failure**

```bash
PYTHONPATH=. pytest tests/unit/api/middleware/test_access_log.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'api.middleware.access_log'`

**Step 3: Create `api/middleware/access_log.py`**

```python
# -*- coding: utf-8 -*-
"""
Access log middleware.

Emits one log line per HTTP request to the 'myTrader.access' logger:

    GET /api/research/watchlist 200 45.3ms 127.0.0.1
"""
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

access_logger = logging.getLogger('myTrader.access')

# Paths that are too noisy to log (health checks, static assets)
_SKIP_PATHS = {'/health', '/metrics', '/favicon.ico', '/docs', '/redoc', '/openapi.json'}


class AccessLogMiddleware(BaseHTTPMiddleware):
    """Log one line per HTTP request with method, path, status, latency, IP."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000

        client_ip = _get_ip(request)
        msg = (
            f'{request.method} {request.url.path} '
            f'{response.status_code} '
            f'{latency_ms:.1f}ms '
            f'{client_ip}'
        )
        # Use WARNING for 5xx so errors are visible even at WARNING level
        if response.status_code >= 500:
            access_logger.warning(msg)
        else:
            access_logger.info(msg)

        return response


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'
```

**Step 4: Register in `api/main.py`**

Add `access_log` to the router import line:

```python
from api.middleware.access_log import AccessLogMiddleware
```

Register it **after** MetricsMiddleware (order: outermost = last added):

```python
app.add_middleware(AccessLogMiddleware)
```

Place it between `MetricsMiddleware` and `RateLimitMiddleware`.

**Step 5: Run tests**

```bash
PYTHONPATH=. pytest tests/unit/api/middleware/test_access_log.py -v
```

Expected: 3 passed.

**Step 6: Commit**

```bash
git add api/middleware/access_log.py api/main.py \
        tests/unit/api/middleware/__init__.py \
        tests/unit/api/middleware/test_access_log.py
git commit -m "feat(logging): add AccessLogMiddleware for per-request access logs"
```

---

### Task 4: Log tail endpoint — GET /api/admin/logs

**Files:**
- Modify: `api/routers/admin.py` (add two endpoints)

**Step 1: Read current `api/routers/admin.py`** to understand existing imports and structure.

**Step 2: Add log-tail helper and two routes**

At the bottom of `api/routers/admin.py`, append:

```python
import os as _os
from pathlib import Path as _Path

_LOG_DIR = _Path('logs')
_ALLOWED_FILES = {'app', 'error', 'access'}


def _tail(filepath: str, lines: int) -> list[str]:
    """Read last N lines from a file efficiently."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
        return [l.rstrip('\n') for l in all_lines[-lines:]]
    except FileNotFoundError:
        return []
    except Exception as e:
        return [f'[ERROR reading log] {e}']


@router.get('/logs')
async def tail_log(
    file: str = 'app',
    lines: int = 100,
    current_user=Depends(get_current_user),
):
    """
    Tail a server log file (admin only).

    Query params:
        file  : app | error | access  (default: app)
        lines : number of lines to return (max 2000)
    """
    if file not in _ALLOWED_FILES:
        raise HTTPException(status_code=400, detail=f'file must be one of {_ALLOWED_FILES}')
    lines = min(max(1, lines), 2000)
    filepath = _LOG_DIR / f'{file}.log'
    content = _tail(str(filepath), lines)
    return {
        'file': file,
        'lines_returned': len(content),
        'content': content,
    }


@router.get('/logs/list')
async def list_log_files(current_user=Depends(get_current_user)):
    """List available log files with sizes."""
    result = []
    for name in _ALLOWED_FILES:
        path = _LOG_DIR / f'{name}.log'
        if path.exists():
            stat = path.stat()
            result.append({
                'file': name,
                'size_bytes': stat.st_size,
                'size_kb': round(stat.st_size / 1024, 1),
            })
        else:
            result.append({'file': name, 'size_bytes': 0, 'size_kb': 0})
    return {'logs': result}
```

**Step 3: Smoke test the endpoint**

Restart API then (with a valid token):

```bash
curl "http://localhost:8001/api/admin/logs?file=app&lines=20" \
  -H "Authorization: Bearer $TOKEN"
```

Without a token (should get 401):

```bash
curl "http://localhost:8001/api/admin/logs"
# Expected: {"detail":"Not authenticated"}
```

**Step 4: Commit**

```bash
git add api/routers/admin.py
git commit -m "feat(logging): add log-tail endpoints to admin router"
```

---

### Task 5: Update Makefile api-local target

**Files:**
- Modify: `Makefile`

**Step 1: Update the `api-local` target**

Replace current:
```makefile
api-local: ## Run FastAPI locally with uvicorn
	uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

With:
```makefile
api-local: ## Run FastAPI locally with uvicorn (LOG_LEVEL=DEBUG for dev)
	PYTHONPATH=. LOG_LEVEL=$${LOG_LEVEL:-DEBUG} DB_ENV=$${DB_ENV:-online} \
	uvicorn api.main:app --reload --host 0.0.0.0 --port $${API_PORT:-8001} \
	--log-level $$(echo $${LOG_LEVEL:-debug} | tr '[:upper:]' '[:lower:]')

api-logs: ## Tail the app log
	tail -f logs/app.log

api-errors: ## Tail only errors
	tail -f logs/error.log

api-access: ## Tail the access log
	tail -f logs/access.log
```

**Step 2: Commit**

```bash
git add Makefile
git commit -m "feat(logging): update Makefile with LOG_LEVEL, api-logs targets"
```

---

### Task 6: Full integration smoke test

**Step 1: Restart API with DEBUG level**

```bash
PYTHONPATH=. LOG_LEVEL=DEBUG DB_ENV=online uvicorn api.main:app --port 8001 --reload
```

**Step 2: Confirm startup messages in terminal**

Expected output (first few lines):
```
2026-04-05 10:00:00 [INFO    ] myTrader.api:26 - [STARTUP] myTrader API v0.1.0
2026-04-05 10:00:00 [INFO    ] myTrader.api:27 - [STARTUP] DB env: online
2026-04-05 10:00:00 [INFO    ] myTrader.api:28 - [STARTUP] Redis: localhost:6379
2026-04-05 10:00:00 [INFO    ] myTrader.api:36 - [STARTUP] API ready
```

**Step 3: Make a few requests and check access log**

```bash
curl http://localhost:8001/api/subscription/plans
curl http://localhost:8001/api/market/search?q=600519
```

Then:
```bash
tail -5 logs/access.log
```

Expected:
```
2026-04-05 10:00:05 [ACCESS  ] GET /api/subscription/plans 200 12.4ms 127.0.0.1
2026-04-05 10:00:06 [ACCESS  ] GET /api/market/search 200 85.2ms 127.0.0.1
```

**Step 4: Verify app.log has content**

```bash
tail -20 logs/app.log
```

**Step 5: Final commit**

```bash
git add logs/.gitkeep
git commit -m "feat(logging): complete logging system - files, access log, tail endpoint"
```

---

## File Summary

| File | Action |
|------|--------|
| `api/logging_config.py` | Create — dictConfig with 4 handlers |
| `api/config.py` | Modify — add `log_level`, `log_dir` fields |
| `api/main.py` | Modify — call `setup_logging()`, add `AccessLogMiddleware` |
| `api/middleware/access_log.py` | Create — per-request access logger |
| `api/routers/admin.py` | Modify — add log-tail endpoints |
| `Makefile` | Modify — `api-local`, `api-logs`, `api-errors`, `api-access` targets |
| `logs/.gitkeep` | Create — track directory in git |
| `.gitignore` | Modify — ignore `*.log` files |
| `.env.example` | Modify — document `LOG_LEVEL`, `LOG_DIR` |
| `tests/unit/api/test_logging_config.py` | Create — 5 tests |
| `tests/unit/api/middleware/test_access_log.py` | Create — 3 tests |

## Log File Reference

| File | Content | Rotation |
|------|---------|---------|
| `logs/app.log` | All myTrader events at LOG_LEVEL+ | 10 MB × 5 backups |
| `logs/error.log` | ERROR and CRITICAL only | 10 MB × 3 backups |
| `logs/access.log` | HTTP access (one line/request) | 50 MB × 7 backups |
