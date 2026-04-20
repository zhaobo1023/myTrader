# -*- coding: utf-8 -*-
"""
ORM Models - import all models here for Alembic auto-detection
"""
from api.models.user import User, UserTier, UserRole
from api.models.subscription import Subscription
from api.models.usage_log import UsageLog
from api.models.api_key import ApiKey
from api.models.strategy import Strategy
from api.models.backtest_job import BacktestJob, JobStatus
from api.models.watchlist import UserWatchlist
from api.models.scan_result import UserScanResult
from api.models.notification_config import UserNotificationConfig
from api.models.theme_pool import (
    ThemePool, ThemePoolStock, ThemePoolScore, ThemePoolVote,
    ThemeStatus, HumanStatus,
)
from api.models.candidate_pool import (
    CandidatePoolStock, CandidateMonitorDaily,
    CandidateStatus, AlertLevel,
)
from api.models.invite_code import InviteCode
from api.models.user_position import UserPosition
from api.models.inbox_message import InboxMessage
from api.models.agent import AgentConversation, AgentMessage
from api.models.trade_operation_log import TradeOperationLog

__all__ = [
    'User', 'UserTier', 'UserRole',
    'Subscription',
    'UsageLog',
    'ApiKey',
    'Strategy',
    'BacktestJob', 'JobStatus',
    'UserWatchlist',
    'UserScanResult',
    'UserNotificationConfig',
    'ThemePool', 'ThemePoolStock', 'ThemePoolScore', 'ThemePoolVote',
    'ThemeStatus', 'HumanStatus',
    'CandidatePoolStock', 'CandidateMonitorDaily',
    'CandidateStatus', 'AlertLevel',
    'InviteCode',
    'UserPosition',
    'InboxMessage',
    'AgentConversation', 'AgentMessage',
    'TradeOperationLog',
]
