# -*- coding: utf-8 -*-
"""
Health check schemas
"""
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    version: str
    db: str
    redis: str
