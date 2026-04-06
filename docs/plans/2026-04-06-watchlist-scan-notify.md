# Watchlist + 五维扫描 + 通知 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用户可添加自选股票，系统每日盘后自动执行五维技术面扫描并通过 Feishu/Webhook 推送信号通知。

**Architecture:**
- 新增 `user_watchlist` + `user_scan_results` + `user_notification_config` 三张表（用户维度隔离）
- 扫描引擎复用已有 `strategist/tech_scan/` 的 `IndicatorCalculator` + `SignalDetector` + `ReportEngine`
- Celery beat 每日 16:30 触发扫描任务，按用户 watchlist 并行扫描，结果写库并推送通知

**Tech Stack:** FastAPI + SQLAlchemy async + aiomysql + Celery + Redis (broker) + Feishu webhook

---

## Task 1: 三张新表的 ORM 模型

**Files:**
- Create: `api/models/watchlist.py`
- Create: `api/models/scan_result.py`
- Create: `api/models/notification_config.py`
- Modify: `api/models/__init__.py` (import 新模型)

**Step 1: 创建 UserWatchlist 模型**

```python
# api/models/watchlist.py
# -*- coding: utf-8 -*-
from datetime import datetime
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from api.dependencies import Base


class UserWatchlist(Base):
    __tablename__ = 'user_watchlist'
    __table_args__ = (
        UniqueConstraint('user_id', 'stock_code', name='uq_user_stock'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, default='')
    note: Mapped[str] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
```

**Step 2: 创建 UserScanResult 模型**

```python
# api/models/scan_result.py
# -*- coding: utf-8 -*-
import json
from datetime import date, datetime
from sqlalchemy import Integer, String, Date, DateTime, Float, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from api.dependencies import Base


class UserScanResult(Base):
    __tablename__ = 'user_scan_results'
    __table_args__ = (
        Index('ix_scan_user_date', 'user_id', 'scan_date'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    stock_code: Mapped[str] = mapped_column(String(20), nullable=False)
    stock_name: Mapped[str] = mapped_column(String(50), nullable=False, default='')
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)

    # 五维评分 (0-10)
    score: Mapped[float] = mapped_column(Float, nullable=True)
    score_label: Mapped[str] = mapped_column(String(20), nullable=True)  # 强势多头/偏多/中性震荡/偏空/强势空头

    # 各维度分数 (JSON: {"ma": 2.5, "macd": 1.5, "kdj": 1.0, "rsi": 0.5, "vol_price": 1.5})
    dimension_scores: Mapped[str] = mapped_column(Text, nullable=True)

    # 信号列表 (JSON: [{"type": "MA5金叉MA20", "severity": "GREEN"}, ...])
    signals: Mapped[str] = mapped_column(Text, nullable=True)

    # 最高警级: RED / YELLOW / GREEN / NONE
    max_severity: Mapped[str] = mapped_column(String(10), nullable=False, default='NONE')

    # 通知是否已发送
    notified: Mapped[bool] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    def get_signals(self) -> list:
        return json.loads(self.signals) if self.signals else []

    def get_dimension_scores(self) -> dict:
        return json.loads(self.dimension_scores) if self.dimension_scores else {}
```

**Step 3: 创建 UserNotificationConfig 模型**

```python
# api/models/notification_config.py
# -*- coding: utf-8 -*-
from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from api.dependencies import Base


class UserNotificationConfig(Base):
    __tablename__ = 'user_notification_configs'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True)

    # Feishu/企业微信 Webhook URL
    webhook_url: Mapped[str] = mapped_column(String(500), nullable=True)

    # 通知触发条件
    notify_on_red: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)    # 红灯信号必通知
    notify_on_yellow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False) # 黄灯信号按需
    notify_on_green: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 绿灯信号

    # 最低触发评分 (0-10, 评分 <= 阈值时才通知, None=不限)
    score_threshold: Mapped[float] = mapped_column(Integer, nullable=True)  # e.g. 4 = 中性以下才通知

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
```

**Step 4: 更新 `api/models/__init__.py`**

```python
from api.models.user import User, UserTier, UserRole
from api.models.subscription import Subscription
from api.models.usage_log import UsageLog
from api.models.api_key import ApiKey
from api.models.strategy import Strategy
from api.models.backtest_job import BacktestJob
from api.models.watchlist import UserWatchlist
from api.models.scan_result import UserScanResult
from api.models.notification_config import UserNotificationConfig

__all__ = [
    'User', 'UserTier', 'UserRole',
    'Subscription',
    'UsageLog',
    'ApiKey',
    'Strategy',
    'BacktestJob',
    'UserWatchlist',
    'UserScanResult',
    'UserNotificationConfig',
]
```

**Step 5: 生成并运行 Alembic 迁移**

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "add watchlist scan notify tables"

# 检查生成的脚本：alembic/versions/xxx_add_watchlist_scan_notify_tables.py
# 确认包含三张表的 create_table

# 执行迁移
alembic upgrade head
```

**Step 6: 验证建表成功**

```bash
python3 -c "
import pymysql
conn = pymysql.connect(host='100.119.128.104', port=3306,
    user='quant_user', password='Quant@2024User', database='wucai_trade')
cur = conn.cursor()
cur.execute('SHOW TABLES LIKE \"user_%\"')
print([r[0] for r in cur.fetchall()])
conn.close()
"
# Expected: ['user_notification_configs', 'user_scan_results', 'user_watchlist']
```

**Step 7: Commit**

```bash
git add api/models/watchlist.py api/models/scan_result.py api/models/notification_config.py api/models/__init__.py alembic/versions/
git commit -m "feat(watchlist): add UserWatchlist, UserScanResult, UserNotificationConfig models + migration"
```

---

## Task 2: Watchlist API 路由

**Files:**
- Create: `api/routers/watchlist.py`
- Create: `api/schemas/watchlist.py`
- Modify: `api/main.py` (注册路由)
- Test: `tests/unit/api/test_watchlist_router.py`

**Step 1: 创建 Schemas**

```python
# api/schemas/watchlist.py
# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class WatchlistAddRequest(BaseModel):
    stock_code: str       # e.g. "600519"
    stock_name: str       # e.g. "贵州茅台"
    note: Optional[str] = None


class WatchlistItem(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    note: Optional[str]
    added_at: datetime

    class Config:
        from_attributes = True


class WatchlistResponse(BaseModel):
    items: List[WatchlistItem]
    total: int
```

**Step 2: 创建 watchlist 路由**

```python
# api/routers/watchlist.py
# -*- coding: utf-8 -*-
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.models.watchlist import UserWatchlist
from api.schemas.watchlist import WatchlistAddRequest, WatchlistItem, WatchlistResponse

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/watchlist', tags=['watchlist'])


@router.get('', response_model=WatchlistResponse)
async def list_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的自选股列表"""
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == current_user.id)
        .order_by(UserWatchlist.added_at.desc())
    )
    items = result.scalars().all()
    return WatchlistResponse(
        items=[WatchlistItem.model_validate(i) for i in items],
        total=len(items),
    )


@router.post('', response_model=WatchlistItem, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    req: WatchlistAddRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """添加股票到自选"""
    # 检查是否已存在
    existing = await db.execute(
        select(UserWatchlist).where(
            UserWatchlist.user_id == current_user.id,
            UserWatchlist.stock_code == req.stock_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'{req.stock_code} already in watchlist',
        )

    item = UserWatchlist(
        user_id=current_user.id,
        stock_code=req.stock_code,
        stock_name=req.stock_name,
        note=req.note,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    logger.info('[WATCHLIST] user=%s added stock=%s', current_user.id, req.stock_code)
    return WatchlistItem.model_validate(item)


@router.delete('/{stock_code}', status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    stock_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """从自选中移除股票"""
    result = await db.execute(
        delete(UserWatchlist).where(
            UserWatchlist.user_id == current_user.id,
            UserWatchlist.stock_code == stock_code,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f'{stock_code} not in watchlist')
    logger.info('[WATCHLIST] user=%s removed stock=%s', current_user.id, stock_code)
```

**Step 3: 在 `api/main.py` 注册路由**

```python
# 在已有 router 导入后添加:
from api.routers.watchlist import router as watchlist_router

# 在 app.include_router 区域添加:
app.include_router(watchlist_router)
```

**Step 4: 写测试**

```python
# tests/unit/api/test_watchlist_router.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


def make_mock_user(user_id=1):
    user = MagicMock()
    user.id = user_id
    user.email = 'test@test.com'
    user.tier = MagicMock(value='free')
    user.role = MagicMock(value='user')
    user.is_active = True
    return user


def test_list_watchlist_empty(client_with_auth):
    """空自选列表返回 total=0"""
    resp = client_with_auth.get('/api/watchlist')
    assert resp.status_code == 200
    data = resp.json()
    assert data['total'] == 0
    assert data['items'] == []


def test_add_stock_to_watchlist(client_with_auth):
    """成功添加股票返回 201"""
    resp = client_with_auth.post('/api/watchlist', json={
        'stock_code': '600519',
        'stock_name': '贵州茅台',
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data['stock_code'] == '600519'
    assert data['stock_name'] == '贵州茅台'


def test_add_duplicate_stock_returns_409(client_with_auth):
    """重复添加返回 409"""
    client_with_auth.post('/api/watchlist', json={'stock_code': '000001', 'stock_name': '平安银行'})
    resp = client_with_auth.post('/api/watchlist', json={'stock_code': '000001', 'stock_name': '平安银行'})
    assert resp.status_code == 409


def test_remove_stock_from_watchlist(client_with_auth):
    """删除已有股票返回 204"""
    client_with_auth.post('/api/watchlist', json={'stock_code': '600036', 'stock_name': '招商银行'})
    resp = client_with_auth.delete('/api/watchlist/600036')
    assert resp.status_code == 204


def test_remove_nonexistent_stock_returns_404(client_with_auth):
    """删除不存在的股票返回 404"""
    resp = client_with_auth.delete('/api/watchlist/999999')
    assert resp.status_code == 404
```

**Step 5: 运行测试**

```bash
PYTHONPATH=. python -m pytest tests/unit/api/test_watchlist_router.py -v
```

**Step 6: Commit**

```bash
git add api/routers/watchlist.py api/schemas/watchlist.py api/main.py tests/unit/api/test_watchlist_router.py
git commit -m "feat(watchlist): add watchlist CRUD API endpoints"
```

---

## Task 3: 通知配置 API

**Files:**
- Create: `api/routers/notification.py`
- Create: `api/schemas/notification.py`
- Modify: `api/main.py`

**Step 1: Schema**

```python
# api/schemas/notification.py
# -*- coding: utf-8 -*-
from typing import Optional
from pydantic import BaseModel, HttpUrl


class NotificationConfigUpdate(BaseModel):
    webhook_url: Optional[str] = None
    notify_on_red: bool = True
    notify_on_yellow: bool = False
    notify_on_green: bool = False
    score_threshold: Optional[float] = None  # 低于此分数才通知
    enabled: bool = True


class NotificationConfigResponse(BaseModel):
    webhook_url: Optional[str]
    notify_on_red: bool
    notify_on_yellow: bool
    notify_on_green: bool
    score_threshold: Optional[float]
    enabled: bool

    class Config:
        from_attributes = True
```

**Step 2: Router**

```python
# api/routers/notification.py
# -*- coding: utf-8 -*-
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.models.notification_config import UserNotificationConfig
from api.schemas.notification import NotificationConfigUpdate, NotificationConfigResponse

router = APIRouter(prefix='/api/notification', tags=['notification'])


@router.get('/config', response_model=NotificationConfigResponse)
async def get_notification_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取通知配置，不存在则返回默认值"""
    result = await db.execute(
        select(UserNotificationConfig).where(UserNotificationConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    if config is None:
        # 返回默认配置（不写库）
        return NotificationConfigResponse(
            webhook_url=None,
            notify_on_red=True,
            notify_on_yellow=False,
            notify_on_green=False,
            score_threshold=None,
            enabled=True,
        )
    return NotificationConfigResponse.model_validate(config)


@router.put('/config', response_model=NotificationConfigResponse)
async def update_notification_config(
    req: NotificationConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建或更新通知配置（upsert）"""
    result = await db.execute(
        select(UserNotificationConfig).where(UserNotificationConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()

    if config is None:
        config = UserNotificationConfig(user_id=current_user.id)
        db.add(config)

    config.webhook_url = req.webhook_url
    config.notify_on_red = req.notify_on_red
    config.notify_on_yellow = req.notify_on_yellow
    config.notify_on_green = req.notify_on_green
    config.score_threshold = req.score_threshold
    config.enabled = req.enabled

    await db.flush()
    await db.refresh(config)
    return NotificationConfigResponse.model_validate(config)
```

**Step 3: 注册路由到 main.py**

```python
from api.routers.notification import router as notification_router
app.include_router(notification_router)
```

**Step 4: Commit**

```bash
git add api/routers/notification.py api/schemas/notification.py api/main.py
git commit -m "feat(notification): add notification config CRUD API"
```

---

## Task 4: 通知发送服务

**Files:**
- Create: `api/services/notification_sender.py`

**Step 1: 实现通知发送服务**

```python
# api/services/notification_sender.py
# -*- coding: utf-8 -*-
"""
发送飞书/Webhook 扫描结果通知
复用 scheduler/alert.py 的 Feishu card 格式，适配用户维度
"""
import logging
import requests
from datetime import date
from typing import List

logger = logging.getLogger('myTrader.api')


def _severity_label(severity: str) -> str:
    mapping = {'RED': '[RED]', 'YELLOW': '[WARN]', 'GREEN': '[OK]', 'NONE': '[--]'}
    return mapping.get(severity, '[--]')


def build_feishu_card(
    stock_code: str,
    stock_name: str,
    scan_date: date,
    score: float,
    score_label: str,
    signals: list,
    max_severity: str,
) -> dict:
    """构建飞书互动卡片消息"""
    severity_tag = _severity_label(max_severity)
    signal_lines = '\n'.join(
        f"- {_severity_label(s.get('severity', 'NONE'))} {s.get('type', '')}"
        for s in signals[:5]  # 最多显示5条信号
    ) or '- 无明显信号'

    content = (
        f"股票: {stock_name}({stock_code})\n"
        f"日期: {scan_date}\n"
        f"五维评分: {score:.1f}/10  {score_label}\n"
        f"信号:\n{signal_lines}"
    )

    color_map = {'RED': 'red', 'YELLOW': 'yellow', 'GREEN': 'green', 'NONE': 'grey'}
    color = color_map.get(max_severity, 'grey')

    return {
        'msg_type': 'interactive',
        'card': {
            'header': {
                'title': {'tag': 'plain_text', 'content': f'{severity_tag} 五维扫描 | {stock_name}'},
                'template': color,
            },
            'elements': [
                {'tag': 'div', 'text': {'tag': 'lark_md', 'content': content}}
            ],
        },
    }


def send_webhook_notification(webhook_url: str, payload: dict) -> bool:
    """发送 Webhook 通知，返回是否成功"""
    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning('[NOTIFY] webhook send failed: %s', e)
        return False


def should_notify(config, max_severity: str, score: float) -> bool:
    """根据用户配置判断是否需要发通知"""
    if not config.enabled or not config.webhook_url:
        return False
    if max_severity == 'RED' and config.notify_on_red:
        return True
    if max_severity == 'YELLOW' and config.notify_on_yellow:
        return True
    if max_severity == 'GREEN' and config.notify_on_green:
        return True
    # 评分阈值触发（低于阈值才通知）
    if config.score_threshold is not None and score <= config.score_threshold:
        return True
    return False
```

**Step 2: 写单元测试**

```python
# tests/unit/api/test_notification_sender.py
from api.services.notification_sender import should_notify, build_feishu_card
from unittest.mock import MagicMock
from datetime import date


def make_config(enabled=True, webhook_url='https://hook.example.com',
                notify_on_red=True, notify_on_yellow=False,
                notify_on_green=False, score_threshold=None):
    c = MagicMock()
    c.enabled = enabled
    c.webhook_url = webhook_url
    c.notify_on_red = notify_on_red
    c.notify_on_yellow = notify_on_yellow
    c.notify_on_green = notify_on_green
    c.score_threshold = score_threshold
    return c


def test_should_notify_red_signal():
    assert should_notify(make_config(notify_on_red=True), 'RED', 3.0) is True


def test_should_not_notify_yellow_by_default():
    assert should_notify(make_config(notify_on_yellow=False), 'YELLOW', 5.0) is False


def test_should_notify_by_score_threshold():
    config = make_config(notify_on_red=False, score_threshold=4.0)
    assert should_notify(config, 'NONE', 3.5) is True
    assert should_notify(config, 'NONE', 5.0) is False


def test_no_notify_when_disabled():
    assert should_notify(make_config(enabled=False), 'RED', 1.0) is False


def test_no_notify_without_webhook():
    assert should_notify(make_config(webhook_url=None), 'RED', 1.0) is False


def test_build_feishu_card_structure():
    card = build_feishu_card(
        stock_code='600519', stock_name='贵州茅台',
        scan_date=date(2026, 4, 6), score=7.5, score_label='偏多',
        signals=[{'type': 'MA5金叉MA20', 'severity': 'GREEN'}],
        max_severity='GREEN',
    )
    assert card['msg_type'] == 'interactive'
    assert '贵州茅台' in card['card']['header']['title']['content']
```

**Step 3: 运行测试**

```bash
PYTHONPATH=. python -m pytest tests/unit/api/test_notification_sender.py -v
```

**Step 4: Commit**

```bash
git add api/services/notification_sender.py tests/unit/api/test_notification_sender.py
git commit -m "feat(notification): add notification sender service with feishu card format"
```

---

## Task 5: Celery 扫描任务

**Files:**
- Create: `api/tasks/watchlist_scan.py`
- Modify: `api/tasks/celery_app.py` (beat schedule)

**Step 1: 实现扫描 Celery 任务**

```python
# api/tasks/watchlist_scan.py
# -*- coding: utf-8 -*-
"""
Celery 任务：对用户 watchlist 执行五维技术面扫描
复用 strategist/tech_scan/ 的 IndicatorCalculator + SignalDetector + ReportEngine
"""
import json
import logging
import os
import sys
from datetime import date, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks.scan')


def _get_sync_db():
    """同步 pymysql 连接（Celery worker 环境，非 async）"""
    import pymysql
    from api.config import get_settings
    settings = get_settings()
    # 根据 DB_ENV 决定连接目标
    if settings.db_env == 'online':
        return pymysql.connect(
            host=settings.online_db_host,
            port=settings.online_db_port,
            user=settings.online_db_user,
            password=settings.online_db_password,
            database=settings.online_db_name,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor,
        )
    return pymysql.connect(
        host=settings.local_db_host,
        port=settings.local_db_port,
        user=settings.local_db_user,
        password=settings.local_db_password,
        database=settings.local_db_name,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
    )


def _run_scan_for_stock(stock_code: str, scan_date: date) -> dict:
    """
    对单只股票执行五维扫描，返回结果 dict。
    复用 strategist/tech_scan/ 模块。
    """
    from strategist.tech_scan.data_fetcher import TechScanDataFetcher
    from strategist.tech_scan.indicator_calculator import IndicatorCalculator
    from strategist.tech_scan.signal_detector import SignalDetector
    from strategist.tech_scan.report_engine import ReportEngine

    fetcher = TechScanDataFetcher()
    calc = IndicatorCalculator()
    detector = SignalDetector()
    engine = ReportEngine()

    # 拉取数据
    df = fetcher.fetch_stock_data(stock_code, end_date=scan_date.strftime('%Y-%m-%d'))
    if df is None or df.empty:
        logger.warning('[SCAN] no data for %s', stock_code)
        return None

    # 计算指标
    df = calc.calc_indicators(df)
    latest = df.iloc[-1]

    # 检测信号
    signals = detector.detect_all(df)

    # 五维评分
    score_result = engine.calc_score(latest)

    # 最高警级
    severity_order = {'RED': 3, 'YELLOW': 2, 'GREEN': 1, 'INFO': 0, 'NONE': -1}
    max_severity = 'NONE'
    for sig in signals:
        sev = sig.get('severity', 'NONE')
        if severity_order.get(sev, -1) > severity_order.get(max_severity, -1):
            max_severity = sev

    return {
        'score': score_result.get('total', 0.0),
        'score_label': score_result.get('label', ''),
        'dimension_scores': json.dumps(score_result.get('dimensions', {})),
        'signals': json.dumps(signals),
        'max_severity': max_severity,
    }


@celery_app.task(name='watchlist_scan.scan_all_users', bind=True)
def scan_all_users_watchlist(self):
    """
    每日盘后触发：对所有用户的 watchlist 执行五维扫描
    """
    today = date.today()
    conn = _get_sync_db()
    try:
        with conn.cursor() as cur:
            # 取所有有 watchlist 的用户
            cur.execute(
                'SELECT DISTINCT user_id FROM user_watchlist'
            )
            user_ids = [r['user_id'] for r in cur.fetchall()]

        logger.info('[SCAN] starting daily scan for %d users', len(user_ids))
        for user_id in user_ids:
            scan_user_watchlist.delay(user_id, today.isoformat())

    finally:
        conn.close()


@celery_app.task(name='watchlist_scan.scan_user', bind=True, max_retries=2)
def scan_user_watchlist(self, user_id: int, scan_date_str: str):
    """
    扫描单个用户的所有 watchlist 股票，写结果，触发通知
    """
    scan_date = date.fromisoformat(scan_date_str)
    conn = _get_sync_db()

    try:
        with conn.cursor() as cur:
            # 取用户 watchlist
            cur.execute(
                'SELECT stock_code, stock_name FROM user_watchlist WHERE user_id = %s',
                (user_id,)
            )
            stocks = cur.fetchall()

            # 取用户通知配置
            cur.execute(
                'SELECT * FROM user_notification_configs WHERE user_id = %s AND enabled = 1',
                (user_id,)
            )
            notify_config = cur.fetchone()

        if not stocks:
            return

        logger.info('[SCAN] user=%d scanning %d stocks', user_id, len(stocks))

        for stock in stocks:
            code = stock['stock_code']
            name = stock['stock_name']
            try:
                result = _run_scan_for_stock(code, scan_date)
                if result is None:
                    continue

                # 写入或更新扫描结果
                with conn.cursor() as cur:
                    cur.execute('''
                        INSERT INTO user_scan_results
                            (user_id, stock_code, stock_name, scan_date, score, score_label,
                             dimension_scores, signals, max_severity, notified)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
                        ON DUPLICATE KEY UPDATE
                            score=VALUES(score), score_label=VALUES(score_label),
                            dimension_scores=VALUES(dimension_scores),
                            signals=VALUES(signals), max_severity=VALUES(max_severity),
                            notified=0
                    ''', (
                        user_id, code, name, scan_date,
                        result['score'], result['score_label'],
                        result['dimension_scores'], result['signals'],
                        result['max_severity'],
                    ))
                    conn.commit()

                # 发通知
                if notify_config:
                    _maybe_send_notification(notify_config, code, name, scan_date, result)

            except Exception as e:
                logger.error('[SCAN] error scanning %s for user=%d: %s', code, user_id, e)
                continue

    finally:
        conn.close()


def _maybe_send_notification(notify_config: dict, stock_code: str, stock_name: str,
                               scan_date: date, result: dict):
    """根据配置判断并发送通知"""
    from api.services.notification_sender import should_notify, build_feishu_card, send_webhook_notification

    class ConfigObj:
        def __init__(self, d):
            self.enabled = bool(d.get('enabled', 1))
            self.webhook_url = d.get('webhook_url')
            self.notify_on_red = bool(d.get('notify_on_red', 1))
            self.notify_on_yellow = bool(d.get('notify_on_yellow', 0))
            self.notify_on_green = bool(d.get('notify_on_green', 0))
            self.score_threshold = d.get('score_threshold')

    config_obj = ConfigObj(notify_config)

    if not should_notify(config_obj, result['max_severity'], result['score']):
        return

    signals = json.loads(result['signals'])
    card = build_feishu_card(
        stock_code=stock_code,
        stock_name=stock_name,
        scan_date=scan_date,
        score=result['score'],
        score_label=result['score_label'],
        signals=signals,
        max_severity=result['max_severity'],
    )
    send_webhook_notification(config_obj.webhook_url, card)
    logger.info('[NOTIFY] sent to user webhook: stock=%s severity=%s', stock_code, result['max_severity'])
```

**Step 2: 更新 Celery Beat Schedule**

在 `api/tasks/celery_app.py` 末尾添加：

```python
from celery.schedules import crontab

# 每个交易日 16:30 执行全量扫描（周一至周五）
celery_app.conf.beat_schedule = {
    'daily-watchlist-scan': {
        'task': 'watchlist_scan.scan_all_users',
        'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),
    },
    'daily-expire-subscriptions': {
        'task': 'expire_subscriptions',
        'schedule': crontab(hour=0, minute=5),
    },
}
celery_app.conf.timezone = 'Asia/Shanghai'
```

**Step 3: 更新 `docker-compose.yml`，添加 Celery worker + beat**

在 `api` service 之后添加：

```yaml
  celery-worker:
    build: .
    command: celery -A api.tasks.celery_app worker -l info -c 4 -Q default
    env_file: .env
    environment:
      - REDIS_HOST=redis
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - .:/app
      - ./output:/app/output
    restart: unless-stopped

  celery-beat:
    build: .
    command: celery -A api.tasks.celery_app beat -l info --scheduler celery.beat.PersistentScheduler
    env_file: .env
    environment:
      - REDIS_HOST=redis
    depends_on:
      redis:
        condition: service_healthy
    volumes:
      - .:/app
    restart: unless-stopped
```

**Step 4: 手动触发测试（开发环境）**

```bash
# 启动 worker（新终端）
PYTHONPATH=. celery -A api.tasks.celery_app worker -l debug

# 触发单用户扫描（另一终端）
PYTHONPATH=. python3 -c "
from api.tasks.watchlist_scan import scan_user_watchlist
from datetime import date
# 同步直接调用（不经过 Celery broker）
scan_user_watchlist(user_id=1, scan_date_str=date.today().isoformat())
"
```

**Step 5: Commit**

```bash
git add api/tasks/watchlist_scan.py api/tasks/celery_app.py docker-compose.yml
git commit -m "feat(scan): add Celery watchlist scan task with beat schedule"
```

---

## Task 6: 扫描结果 API

**Files:**
- Create: `api/routers/scan_results.py`
- Create: `api/schemas/scan_result.py`
- Modify: `api/main.py`

**Step 1: Schema**

```python
# api/schemas/scan_result.py
# -*- coding: utf-8 -*-
import json
from datetime import date, datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, field_validator


class ScanResultItem(BaseModel):
    id: int
    stock_code: str
    stock_name: str
    scan_date: date
    score: Optional[float]
    score_label: Optional[str]
    dimension_scores: Optional[Dict[str, Any]]
    signals: Optional[List[Dict[str, Any]]]
    max_severity: str
    notified: bool
    created_at: datetime

    class Config:
        from_attributes = True

    @field_validator('dimension_scores', mode='before')
    @classmethod
    def parse_dimension_scores(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator('signals', mode='before')
    @classmethod
    def parse_signals(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v
```

**Step 2: Router**

```python
# api/routers/scan_results.py
# -*- coding: utf-8 -*-
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.models.scan_result import UserScanResult
from api.schemas.scan_result import ScanResultItem

router = APIRouter(prefix='/api/scan-results', tags=['scan-results'])


@router.get('', response_model=List[ScanResultItem])
async def list_scan_results(
    scan_date: Optional[date] = Query(None, description='指定日期，不传则返回最新'),
    severity: Optional[str] = Query(None, description='过滤警级: RED/YELLOW/GREEN'),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的扫描结果"""
    query = select(UserScanResult).where(UserScanResult.user_id == current_user.id)

    if scan_date:
        query = query.where(UserScanResult.scan_date == scan_date)
    else:
        # 取最新一次扫描日期的结果
        latest_date_q = (
            select(UserScanResult.scan_date)
            .where(UserScanResult.user_id == current_user.id)
            .order_by(UserScanResult.scan_date.desc())
            .limit(1)
        )
        latest_result = await db.execute(latest_date_q)
        latest_date = latest_result.scalar_one_or_none()
        if latest_date:
            query = query.where(UserScanResult.scan_date == latest_date)

    if severity:
        query = query.where(UserScanResult.max_severity == severity.upper())

    query = query.order_by(UserScanResult.score.asc())  # 评分低的（风险高）排前面
    result = await db.execute(query)
    return [ScanResultItem.model_validate(r) for r in result.scalars().all()]
```

**Step 3: 注册 + Commit**

```python
# api/main.py
from api.routers.scan_results import router as scan_results_router
app.include_router(scan_results_router)
```

```bash
git add api/routers/scan_results.py api/schemas/scan_result.py api/main.py
git commit -m "feat(scan): add scan results query API"
```

---

## Task 7: nginx 域名 + Let's Encrypt HTTPS 配置

**Files:**
- Modify: `nginx.conf`
- Create: `scripts/renew-cert.sh`
- Modify: `docker-compose.yml` (certbot service)

**Step 1: 更新 `nginx.conf`（支持域名 + HTTPS）**

```nginx
# nginx.conf
# 将 YOUR_DOMAIN 替换为实际域名，例如 mytrader.app

# HTTP → HTTPS 重定向
server {
    listen 80;
    server_name YOUR_DOMAIN www.YOUR_DOMAIN;

    # Let's Encrypt ACME challenge
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

# HTTPS 主服务
server {
    listen 443 ssl http2;
    server_name YOUR_DOMAIN www.YOUR_DOMAIN;

    ssl_certificate     /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;
    add_header          Strict-Transport-Security "max-age=31536000" always;

    # API 反向代理
    location /api/ {
        proxy_pass         http://api:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    location /health {
        proxy_pass http://api:8000/health;
    }

    # 前端静态资源（Next.js build output）
    location / {
        proxy_pass         http://frontend:3000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
    }
}
```

**Step 2: 添加 certbot 服务到 docker-compose.yml**

```yaml
  certbot:
    image: certbot/certbot
    volumes:
      - certbot_conf:/etc/letsencrypt
      - certbot_www:/var/www/certbot
    entrypoint: >
      sh -c "certbot certonly --webroot -w /var/www/certbot
             -d YOUR_DOMAIN -d www.YOUR_DOMAIN
             --email YOUR_EMAIL --agree-tos --no-eff-email
             --non-interactive"
    profiles: ['certbot']  # 手动运行: docker compose --profile certbot up certbot

# 在 nginx service 的 volumes 中添加:
# - certbot_conf:/etc/letsencrypt:ro
# - certbot_www:/var/www/certbot

# 在 volumes 区域添加:
# certbot_conf:
# certbot_www:
```

**Step 3: 申请证书 + 自动续期**

```bash
# 1. 首次申请证书（域名 DNS 需已解析到服务器）
docker compose --profile certbot up certbot

# 2. 创建续期脚本
# scripts/renew-cert.sh:
#!/bin/bash
docker compose run --rm certbot renew
docker compose exec nginx nginx -s reload
```

```bash
# 3. 加入 crontab 自动续期（每月1日）
# 0 3 1 * * /path/to/myTrader/scripts/renew-cert.sh >> /var/log/cert-renew.log 2>&1
```

**Step 4: Commit**

```bash
git add nginx.conf scripts/renew-cert.sh docker-compose.yml
git commit -m "feat(deploy): add domain HTTPS nginx config + certbot auto-renewal"
```

---

## Task 8: 前端自选股页面

**Files:**
- Create: `web/src/app/(dashboard)/watchlist/page.tsx`
- Create: `web/src/components/watchlist/WatchlistCard.tsx`
- Create: `web/src/components/watchlist/AddStockModal.tsx`

**Step 1: API Client 方法**

在 `web/src/lib/api-client.ts` 中添加 watchlist 相关方法（在已有 axios instance 基础上）：

```typescript
// 添加到 web/src/lib/api-client.ts

export const watchlistApi = {
  list: () => apiClient.get('/api/watchlist'),
  add: (stock_code: string, stock_name: string, note?: string) =>
    apiClient.post('/api/watchlist', { stock_code, stock_name, note }),
  remove: (stock_code: string) =>
    apiClient.delete(`/api/watchlist/${stock_code}`),
};

export const scanResultsApi = {
  list: (params?: { scan_date?: string; severity?: string }) =>
    apiClient.get('/api/scan-results', { params }),
};
```

**Step 2: 自选股页面骨架**

```tsx
// web/src/app/(dashboard)/watchlist/page.tsx
'use client';

import { useState, useEffect } from 'react';
import { watchlistApi, scanResultsApi } from '@/lib/api-client';

interface WatchlistItem {
  id: number;
  stock_code: string;
  stock_name: string;
  note?: string;
  added_at: string;
}

interface ScanResult {
  stock_code: string;
  stock_name: string;
  scan_date: string;
  score: number;
  score_label: string;
  max_severity: string;
  signals: Array<{ type: string; severity: string }>;
}

const SEVERITY_STYLE: Record<string, string> = {
  RED: 'bg-red-100 text-red-700 border-red-200',
  YELLOW: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  GREEN: 'bg-green-100 text-green-700 border-green-200',
  NONE: 'bg-gray-100 text-gray-500 border-gray-200',
};

export default function WatchlistPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [scanResults, setScanResults] = useState<Record<string, ScanResult>>({});
  const [addCode, setAddCode] = useState('');
  const [addName, setAddName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadData = async () => {
    const [wRes, sRes] = await Promise.all([
      watchlistApi.list(),
      scanResultsApi.list(),
    ]);
    setWatchlist(wRes.data.items);
    const resultMap: Record<string, ScanResult> = {};
    for (const r of sRes.data) {
      resultMap[r.stock_code] = r;
    }
    setScanResults(resultMap);
  };

  useEffect(() => { loadData(); }, []);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await watchlistApi.add(addCode.trim(), addName.trim());
      setAddCode('');
      setAddName('');
      await loadData();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } };
      setError(e.response?.data?.detail || 'Add failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRemove = async (code: string) => {
    await watchlistApi.remove(code);
    await loadData();
  };

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6">自选股</h1>

      {/* 添加表单 */}
      <form onSubmit={handleAdd} className="flex gap-2 mb-6">
        <input
          type="text" placeholder="股票代码 (e.g. 600519)" value={addCode}
          onChange={(e) => setAddCode(e.target.value)} required
          className="border rounded px-3 py-2 text-sm w-40"
        />
        <input
          type="text" placeholder="股票名称" value={addName}
          onChange={(e) => setAddName(e.target.value)} required
          className="border rounded px-3 py-2 text-sm w-32"
        />
        <button type="submit" disabled={loading}
          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:bg-blue-300">
          + 加入自选
        </button>
      </form>
      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      {/* 股票列表 */}
      <div className="space-y-3">
        {watchlist.map((item) => {
          const scan = scanResults[item.stock_code];
          const severity = scan?.max_severity || 'NONE';
          return (
            <div key={item.id}
              className={`border rounded-lg p-4 flex items-center justify-between ${SEVERITY_STYLE[severity]}`}>
              <div>
                <span className="font-bold">{item.stock_name}</span>
                <span className="text-gray-500 text-sm ml-2">({item.stock_code})</span>
                {scan && (
                  <span className="ml-3 text-sm">
                    五维评分: <strong>{scan.score?.toFixed(1)}</strong>/10
                    <span className="ml-1 text-xs">{scan.score_label}</span>
                  </span>
                )}
              </div>
              <button onClick={() => handleRemove(item.stock_code)}
                className="text-gray-400 hover:text-red-500 text-sm ml-4">
                移除
              </button>
            </div>
          );
        })}
        {watchlist.length === 0 && (
          <p className="text-gray-400 text-sm">暂无自选股，请添加</p>
        )}
      </div>
    </div>
  );
}
```

**Step 3: Commit**

```bash
git add web/src/app/\(dashboard\)/watchlist/ web/src/lib/api-client.ts
git commit -m "feat(frontend): add watchlist page with scan results display"
```

---

## 执行顺序与依赖关系

```
Task 1 (DB Models + Migration)
  └── Task 2 (Watchlist API)
  └── Task 3 (Notification Config API)
  └── Task 4 (Notification Service)
  └── Task 5 (Celery Scan Task)  ← depends on Task 4
  └── Task 6 (Scan Results API)
Task 7 (nginx + domain)  ← 独立，可并行
Task 8 (Frontend)  ← depends on Task 2 + Task 6
```

---

## 环境变量补充（`.env.example`）

```bash
# Celery
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# 全局告警 Webhook（Scheduler 用）
ALERT_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
```
