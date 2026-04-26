# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Model - WeChat Feed (公众号订阅)
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Text,
)

from api.dependencies import Base


class WechatFeed(Base):
    __tablename__ = 'wechat_feeds'

    id = Column(Integer, primary_key=True, autoincrement=True)
    feed_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String(1024), nullable=True)
    is_active = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<WechatFeed feed_id={self.feed_id} name={self.name}>'
