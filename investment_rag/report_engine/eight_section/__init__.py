# -*- coding: utf-8 -*-
"""
EightSectionAnalyzer - 八章节全面分析引擎

Usage:
    analyzer = EightSectionAnalyzer(db_env='online')
    result = analyzer.generate('688220.SH', '翱捷科技')
    print(result['full_report'])
    print(result['file_path'])
"""
import logging
from typing import Callable, Dict, Optional

from .data_collector import EightSectionDataCollector
from .section_generator import EightSectionGenerator
from .report_assembler import EightSectionAssembler

logger = logging.getLogger(__name__)


class EightSectionAnalyzer:
    """Eight-section comprehensive analysis engine."""

    def __init__(self, db_env: str = "online"):
        self._collector = EightSectionDataCollector(db_env=db_env)
        self._generator = EightSectionGenerator()
        self._assembler = EightSectionAssembler()
        self._db_env = db_env

    def generate(
        self,
        stock_code: str,
        stock_name: str,
        on_step_start: Optional[Callable] = None,
        on_step_done: Optional[Callable] = None,
    ) -> Dict[str, str]:
        """
        Generate eight-section analysis report.

        Args:
            stock_code: Stock code with suffix, e.g. '688220.SH'
            stock_name: Stock name, e.g. '翱捷科技'
            on_step_start: Optional callback(step_id, step_name)
            on_step_done: Optional callback(step_id, step_name, content)

        Returns:
            Dict with keys:
                - full_report: Complete Markdown report
                - file_path: Path to written file
                - data_completeness: Data completeness check result
        """
        logger.info("[EightSection] Starting analysis for %s (%s)", stock_name, stock_code)

        # Step 1: Collect data
        if on_step_start:
            on_step_start("data", "数据收集")
        data = self._collector.collect(stock_code, stock_name)
        if on_step_done:
            on_step_done("data", "数据收集", "OK")

        # Step 2: Generate chapters
        chapters: Dict[str, str] = {}

        steps = [
            ("ch1", "公司概览", lambda: self._generator.render_chapter1(data)),
            ("ch2", "财报分析", lambda: self._generator.generate_chapter2(data, stock_name, stock_code)),
            ("ch3", "可比公司", lambda: self._generator.render_chapter3(data)),
            ("ch4", "DCF估值", lambda: self._generator.generate_chapter4(data, stock_name, stock_code)),
            ("ch5_6", "竞争格局与行业", lambda: self._generator.generate_chapter5_6(data, stock_name, stock_code)),
            ("ch7", "技术面与动量", lambda: self._generator.render_chapter7(data)),
            ("ch8", "投资观点卡片",
             lambda: self._generator.generate_chapter8(data, stock_name, stock_code, chapters)),
        ]

        for step_id, step_name, fn in steps:
            if on_step_start:
                on_step_start(step_id, step_name)
            try:
                content = fn()
                chapters[step_id] = content
                logger.info("[EightSection] %s done, %d chars", step_name, len(content))
            except Exception as e:
                logger.error("[EightSection] %s failed: %s", step_name, e)
                chapters[step_id] = f"## {step_name}\n\n[生成失败: {e}]"
            if on_step_done:
                on_step_done(step_id, step_name, chapters[step_id])

        # Step 3: Assemble report
        full_report = self._assembler.assemble(stock_code, stock_name, chapters)

        # Step 4: Write to file
        file_path = self._assembler.write_to_file(stock_name, full_report)
        logger.info("[EightSection] Report written to %s", file_path)

        return {
            "full_report": full_report,
            "file_path": file_path,
            "data_completeness": data.get("data_completeness", ""),
        }
