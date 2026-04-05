# -*- coding: utf-8 -*-
"""
ReportStore - 研报持久化存储

保存生成的 Markdown 研报到 output/rag/reports/，
维护 index.json 供 API 列举。
"""
import json
import logging
import os
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORT_DIR = os.path.join(ROOT, "output", "rag", "reports")
INDEX_FILE = os.path.join(REPORT_DIR, "index.json")


class ReportStore:
    """研报文件持久化"""

    def __init__(self):
        os.makedirs(REPORT_DIR, exist_ok=True)

    def save(
        self,
        stock_code: str,
        stock_name: str,
        report_type: str,
        content: str,
    ) -> str:
        """
        保存研报 Markdown 文件。

        Returns:
            report_id (str): 唯一标识，格式 {stock_code}_{type}_{date}_{uuid8}
        """
        today = date.today().isoformat()
        short_id = uuid.uuid4().hex[:8]
        report_id = f"{stock_code}_{report_type}_{today}_{short_id}"
        filename = f"{report_id}.md"
        filepath = os.path.join(REPORT_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(content)

        self._append_index(report_id, stock_code, stock_name, report_type, filename)
        logger.info("[ReportStore] Saved: %s", filepath)
        return report_id

    def get(self, report_id: str) -> Optional[str]:
        """读取研报内容，不存在返回 None"""
        entry = next(
            (r for r in self._load_index() if r["id"] == report_id), None
        )
        if not entry:
            return None
        filepath = os.path.join(REPORT_DIR, entry["filename"])
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()

    def list_reports(
        self,
        stock_code: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """列举研报，按创建时间倒序"""
        index = self._load_index()
        if stock_code:
            index = [r for r in index if r.get("stock_code") == stock_code]
        index.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return index[:limit]

    def _load_index(self) -> List[Dict]:
        if not os.path.exists(INDEX_FILE):
            return []
        with open(INDEX_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _append_index(
        self,
        report_id: str,
        stock_code: str,
        stock_name: str,
        report_type: str,
        filename: str,
    ) -> None:
        index = self._load_index()
        index.append({
            "id": report_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_type": report_type,
            "filename": filename,
            "created_at": datetime.now().isoformat(),
        })
        with open(INDEX_FILE, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)
