"""
巨潮资讯（cninfo）年报 PDF 下载器
官方披露平台，合法下载，无版权问题

依赖：pip install requests beautifulsoup4 lxml
"""

import requests
import time
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
    "Origin": "https://www.cninfo.com.cn",
}

PDF_DIR = Path("/Users/zhaobo/Documents/PDF资料/投资研究/公司研究/annual_reports")


def search_announcements(stock_code: str, stock_name: str,
                         ann_type: str = "年报",
                         start_date: str = "2020-01-01",
                         end_date: str = None) -> list[dict]:
    """
    Search cninfo announcements via fulltextSearch API.

    The old hisAnnouncement/query endpoint stopped returning results.
    The new fulltextSearch/full endpoint works as of 2026-04.

    Returns: [{title, date, url, size_kb, code, name, ann_type}, ...]
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # Build search keywords based on report type
    type_keywords = {
        "年报": "年度报告",
        "半年报": "半年度报告",
        "一季报": "第一季度报告",
        "三季报": "第三季度报告",
    }
    keyword = type_keywords.get(ann_type, ann_type)

    url = "https://www.cninfo.com.cn/new/fulltextSearch/full"
    payload = {
        "searchkey": f"{stock_name} {keyword}",
        "sdate": start_date,
        "edate": end_date,
        "isfulltext": "false",
        "sortName": "pubdate",
        "sortType": "desc",
        "pageNum": "1",
        "pageSize": "30",
    }

    results = []
    try:
        resp = requests.post(url, data=payload, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        announcements = data.get("announcements") or []
        for ann in announcements:
            # Filter by stock code
            if ann.get("secCode") != stock_code:
                continue

            title = ann.get("announcementTitle", "")
            # Remove HTML highlight tags
            title = title.replace("<em>", "").replace("</em>", "")

            # Filter: only full reports, exclude summary/supplement/English
            if any(kw in title for kw in ["摘要", "英文", "补充", "更正", "说明"]):
                continue
            if ann_type == "年报" and ("年度报告" not in title or "半年度报告" in title):
                continue
            if ann_type == "半年报" and "半年度报告" not in title:
                continue

            adjunct_url = ann.get("adjunctUrl", "")
            if not adjunct_url:
                continue

            # Parse date from millisecond timestamp
            ann_time = ann.get("announcementTime", 0)
            if ann_time:
                date_str = datetime.fromtimestamp(
                    ann_time / 1000
                ).strftime("%Y-%m-%d")
            else:
                date_str = ""

            results.append({
                "title":    title,
                "date":     date_str,
                "url":      f"http://static.cninfo.com.cn/{adjunct_url}",
                "size_kb":  ann.get("adjunctSize", 0),
                "code":     stock_code,
                "name":     stock_name,
                "ann_type": ann_type,
            })

        logger.info(f"[{stock_code}] {ann_type} search: {len(results)} results")
    except Exception as e:
        logger.error(f"[{stock_code}] search failed: {e}")

    return results


def download_pdf(ann: dict, output_dir: Path, overwrite: bool = False) -> Optional[Path]:
    """
    下载单个 PDF
    文件名格式：{公司名}_{年份}_{公告类型}.pdf
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 从标题提取年份
    year_match = re.search(r"(20\d{2})", ann["title"])
    year = year_match.group(1) if year_match else ann["date"][:4]

    filename = f"{ann['name']}_{ann['code']}_{year}_{ann['ann_type']}.pdf"
    filepath = output_dir / filename

    if filepath.exists() and not overwrite:
        logger.info(f"  已存在，跳过：{filename}")
        return filepath

    try:
        resp = requests.get(ann["url"], headers=HEADERS, timeout=60, stream=True)
        resp.raise_for_status()

        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = filepath.stat().st_size / 1024 / 1024
        logger.info(f"  下载完成：{filename}（{size_mb:.1f} MB）")
        return filepath

    except Exception as e:
        logger.error(f"  下载失败 [{ann['title']}]: {e}")
        if filepath.exists():
            filepath.unlink()
        return None


def batch_download(watch_list: dict,
                   ann_types: list[str] = None,
                   start_year: int = 2021,
                   interval: float = 2.0) -> list[Path]:
    """
    批量下载关注列表的年报/季报
    watch_list: {stock_code: stock_name}
    ann_types: ["年报", "半年报"] 等
    """
    if ann_types is None:
        ann_types = ["年报"]  # 默认只下年报

    start_date = f"{start_year}-01-01"
    downloaded = []

    for code, name in watch_list.items():
        logger.info(f"===== {name}（{code}）=====")
        for ann_type in ann_types:
            anns = search_announcements(code, name, ann_type, start_date)
            for ann in anns:
                path = download_pdf(ann, PDF_DIR / code)
                if path:
                    downloaded.append(path)
                time.sleep(interval)

    logger.info(f"\n全部下载完成，共 {len(downloaded)} 份")
    return downloaded


# --- PDF -> Markdown（配合 MinerU 或 PyMuPDF）---------------------------------

def pdf_to_markdown_pymupdf(pdf_path: Path) -> str:
    """
    用 PyMuPDF 提取文本，保留页码信息
    适合文字版 PDF；扫描版需要用 MinerU

    pip install pymupdf
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(pdf_path))
        pages_text = []

        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text")
            if text.strip():
                pages_text.append(f"\n<!-- page {page_num} -->\n{text}")

        doc.close()
        return "\n".join(pages_text)

    except ImportError:
        logger.error("请安装 PyMuPDF: pip install pymupdf")
        return ""


def extract_key_sections(full_text: str) -> dict:
    """
    从年报全文中提取关键章节
    银行年报重点章节：管理层讨论与分析、财务报表、风险管理
    这些章节是 RAG 最有价值的内容
    """
    sections = {}

    # 常见章节标题模式
    section_patterns = {
        "管理层讨论": r"管理层讨论与分析(.{0,50000}?)(?=第[四五六七]节|重要事项)",
        "风险管理":   r"风险管理(.{0,30000}?)(?=资本管理|第[四五六七]节)",
        "资本充足率": r"资本充足率(.{0,10000}?)(?=\n第|\n[一二三四五六]、)",
        "不良贷款":   r"不良贷款(.{0,10000}?)(?=\n第|\n[一二三四五六]、)",
    }

    for key, pattern in section_patterns.items():
        match = re.search(pattern, full_text, re.DOTALL)
        if match:
            sections[key] = match.group(0)[:5000]  # 截取前5000字

    return sections


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    # 示例：下载华夏银行近4年年报
    watch = {"600015": "华夏银行", "600036": "招商银行"}
    paths = batch_download(watch, ann_types=["年报"], start_year=2021)
    print(f"\n下载完成：{[str(p) for p in paths]}")
