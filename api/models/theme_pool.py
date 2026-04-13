# -*- coding: utf-8 -*-
"""
SQLAlchemy ORM Models - Theme Pool (thematic stock selection)

Tables:
- theme_pools: thematic pool master table
- theme_pool_stocks: stocks in each pool
- theme_pool_scores: daily auto-scoring snapshots
- theme_pool_votes: user votes on stocks
"""
import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Double,
    Enum, ForeignKey, SmallInteger, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship

from api.dependencies import Base


# ------------------------------------------------------------------
# Enums
# ------------------------------------------------------------------

class ThemeStatus(str, enum.Enum):
    DRAFT = 'draft'
    ACTIVE = 'active'
    ARCHIVED = 'archived'


class HumanStatus(str, enum.Enum):
    NORMAL = 'normal'
    FOCUSED = 'focused'
    WATCHING = 'watching'
    EXCLUDED = 'excluded'


# ------------------------------------------------------------------
# Theme Pool master table
# ------------------------------------------------------------------

class ThemePool(Base):
    __tablename__ = 'theme_pools'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        Enum('draft', 'active', 'archived', name='themestatus'),
        default='draft', nullable=False,
    )
    created_by = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # relationships
    creator = relationship('User', foreign_keys=[created_by])
    stocks = relationship('ThemePoolStock', back_populates='theme', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ThemePool id={self.id} name={self.name} status={self.status}>'


# ------------------------------------------------------------------
# Stocks in a theme pool
# ------------------------------------------------------------------

class ThemePoolStock(Base):
    __tablename__ = 'theme_pool_stocks'
    __table_args__ = (
        UniqueConstraint('theme_id', 'stock_code', name='uq_theme_stock'),
        Index('ix_theme_pool_stocks_theme_id', 'theme_id'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    theme_id = Column(Integer, ForeignKey('theme_pools.id', ondelete='CASCADE'), nullable=False)
    stock_code = Column(String(20), nullable=False)
    stock_name = Column(String(50), nullable=False, default='')
    recommended_by = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    reason = Column(Text, nullable=True)
    entry_price = Column(Double, nullable=True)
    entry_date = Column(Date, nullable=False)
    human_status = Column(
        Enum('normal', 'focused', 'watching', 'excluded', name='humanstatus'),
        default='normal', nullable=False,
    )
    note = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # relationships
    theme = relationship('ThemePool', back_populates='stocks')
    recommender = relationship('User', foreign_keys=[recommended_by])
    scores = relationship('ThemePoolScore', back_populates='stock', cascade='all, delete-orphan')
    votes = relationship('ThemePoolVote', back_populates='stock', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ThemePoolStock id={self.id} code={self.stock_code} theme={self.theme_id}>'


# ------------------------------------------------------------------
# Daily scoring snapshots
# ------------------------------------------------------------------

class ThemePoolScore(Base):
    __tablename__ = 'theme_pool_scores'
    __table_args__ = (
        UniqueConstraint('theme_stock_id', 'score_date', name='uq_stock_score_date'),
        Index('ix_theme_pool_scores_date', 'score_date'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    theme_stock_id = Column(Integer, ForeignKey('theme_pool_stocks.id', ondelete='CASCADE'), nullable=False)
    score_date = Column(Date, nullable=False)

    # RPS scores
    rps_20 = Column(Double, nullable=True)
    rps_60 = Column(Double, nullable=True)
    rps_120 = Column(Double, nullable=True)
    rps_250 = Column(Double, nullable=True)

    # technical score
    tech_score = Column(Double, nullable=True)
    tech_signals = Column(Text, nullable=True)  # JSON string

    # fundamental score
    fundamental_score = Column(Double, nullable=True)
    fundamental_data = Column(Text, nullable=True)  # JSON string

    # weighted total
    total_score = Column(Double, nullable=True)

    # return tracking (from entry_price)
    return_5d = Column(Double, nullable=True)
    return_10d = Column(Double, nullable=True)
    return_20d = Column(Double, nullable=True)
    return_60d = Column(Double, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # relationships
    stock = relationship('ThemePoolStock', back_populates='scores')

    def __repr__(self):
        return f'<ThemePoolScore stock={self.theme_stock_id} date={self.score_date}>'


# ------------------------------------------------------------------
# User votes on stocks
# ------------------------------------------------------------------

class ThemePoolVote(Base):
    __tablename__ = 'theme_pool_votes'
    __table_args__ = (
        UniqueConstraint('theme_stock_id', 'user_id', name='uq_stock_user_vote'),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    theme_stock_id = Column(Integer, ForeignKey('theme_pool_stocks.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    vote = Column(SmallInteger, nullable=False)  # 1=up, -1=down
    voted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # relationships
    stock = relationship('ThemePoolStock', back_populates='votes')
    user = relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return f'<ThemePoolVote stock={self.theme_stock_id} user={self.user_id} vote={self.vote}>'
