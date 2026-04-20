# -*- coding: utf-8 -*-
"""
风控 V2 业务逻辑层

RiskService 封装对 data_analyst.risk_assessment 模块的调用，供路由层使用。
"""
import logging

from data_analyst.risk_assessment.storage import dataclass_to_dict, reconstruct_layered_result

logger = logging.getLogger('myTrader.api')


class RiskService:
    """风控扫描服务，提供静态方法供 API 路由调用。"""

    @staticmethod
    def run_scan(user_id: int, env: str = 'online') -> dict:
        """
        执行完整分层风控扫描（L1-L5），返回序列化后的 dict。

        Args:
            user_id: 当前用户 ID，用于查询持仓数据
            env: 数据库环境，默认 'online'

        Returns:
            LayeredRiskResult 序列化后的 dict
        """
        from data_analyst.risk_assessment.scanner import scan_portfolio_v2
        result = scan_portfolio_v2(user_id=user_id, env=env)
        return dataclass_to_dict(result)

    @staticmethod
    def get_report(user_id: int, env: str = 'online') -> str:
        """
        获取最新风控扫描 Markdown 报告。
        优先从 output/risk_assessment/ 加载缓存，否则实时计算。

        Args:
            user_id: 当前用户 ID，缓存不可用时用于实时扫描
            env: 数据库环境，默认 'online'

        Returns:
            Markdown 格式的风控报告字符串
        """
        from data_analyst.risk_assessment.storage import load_scan_result
        from data_analyst.risk_assessment.report import generate_report_v2

        cached = load_scan_result()
        if cached is not None:
            try:
                layered = reconstruct_layered_result(cached)
                logger.info('[RISK_SERVICE] 从缓存加载报告: scan_time=%s', cached['scan_time'])
                return generate_report_v2(layered)
            except Exception as e:
                logger.warning('[RISK_SERVICE] 缓存重建失败，实时计算: %s', e)

        from data_analyst.risk_assessment.scanner import scan_portfolio_v2
        result = scan_portfolio_v2(user_id=user_id, env=env)
        logger.info('[RISK_SERVICE] 实时计算报告: overall_score=%.1f', result.overall_score)
        return generate_report_v2(result)

    @staticmethod
    def check_deps(env: str = 'online') -> list:
        """
        检查各数据依赖的新鲜度，必要时触发更新。

        Args:
            env: 数据库环境，默认 'online'

        Returns:
            DataStatus 列表（序列化后）
        """
        from data_analyst.risk_assessment.data_deps import DataDependencyChecker
        results = DataDependencyChecker(env=env).check_and_trigger()
        return dataclass_to_dict(results)
