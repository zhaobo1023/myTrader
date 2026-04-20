# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod


class BaseAssessor(ABC):
    def __init__(self, env: str = 'online'):
        self.env = env

    def _query(self, sql: str, params=None) -> list:
        from config.db import execute_query
        return list(execute_query(sql, params or (), env=self.env))

    @abstractmethod
    def assess(self, *args, **kwargs):
        pass
