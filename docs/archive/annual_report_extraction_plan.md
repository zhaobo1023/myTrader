# 年报数据提取与研报增强方案

> 2026-04-08 | 基于华夏银行案例复盘的系统化改进计划
> v1.1 更新：新增 PDF→Markdown 转换方案（MinerU）

---

## 〇、PDF→Markdown 转换方案

### 0.1 为什么需要转 Markdown

年报原始文件为 PDF，但 PDF 直接用于：
- **Embedding**：PyMuPDF 提取的纯文本丢失表格结构，表格数字变成混乱的一行行数字
- **结构化提取**：正则匹配需要可靠的文本格式，PDF 的文本流不可预测

转为 Markdown 后：
- 表格变成标准 `| col1 | col2 |` 格式，**正则提取极其简单**
- 段落和标题保留层级，**embedding 分块质量高**
- 一份 md 文件同时服务通路 A（Embedding）和通路 B（结构化提取）

```
年报PDF --[MinerU]--> 年报Markdown --+--> [通路A] Embedding → ChromaDB
                                     |
                                     +--> [通路B] 正则/表格提取 → MySQL
```

### 0.2 工具选型

调研了 5 款主流 PDF→MD 工具，针对**中文财报**场景评估：

| 工具 | 中文支持 | 表格精度 | 本地运行 | 速度 | 许可证 |
|------|---------|---------|---------|------|--------|
| **MinerU 3.0** | 极好 (PaddleOCR) | 极好 (OmniDocBench 90.67) | 是 | 中 | AGPL-3.0 |
| Marker | 好 (Surya OCR) | 好（需LLM增强） | 部分（LLM需云端） | 快 | 受限商用 |
| Docling (IBM) | 弱（英文为主） | 好（英文） | 是 | 快 | MIT |
| PyMuPDF4LLM | 尚可（原生PDF） | 基础（复杂表格差） | 是 | 极快 | AGPL-3.0 |
| MarkItDown (MS) | 差 | 差（表格结构破坏） | 是 | 极快 | MIT |

**结论：MinerU 3.0（上海 AI Lab 出品）是中文财报场景的最佳选择。**

核心优势：
- **PaddleOCR PP-OCRv4**：中文 OCR 最强方案，支持 109 种语言
- **TableMaster + StructEqTable**：表格识别精度在 OmniDocBench 排行榜第一
- **完全本地运行**：财报数据不出本机，支持 Apple Silicon MPS 加速
- **活跃维护**：2026-03-29 发布 v3.0.0

### 0.3 安装与使用

```bash
# 安装
pip install mineru

# 单文件转换（中文模式）
mineru -p "华夏银行_600015_2025_年报.pdf" -o output/ --lang ch

# 批量转换（目录下所有PDF）
for f in /path/to/annual_reports/600015/*.pdf; do
    mineru -p "$f" -o /path/to/annual_reports/600015/md/ --lang ch
done
```

### 0.4 预期产出

```
annual_reports/600015/
├── 华夏银行_600015_2025_年报.pdf          # 原始 PDF（11MB）
├── 华夏银行_600015_2025_年报.txt          # 已有的txt（622KB）
└── md/                                    # MinerU 产出
    ├── 华夏银行_600015_2025_年报.md       # Markdown 正文
    └── images/                            # 提取的图表（可选）
```

Markdown 中的表格示例（预期效果）：

```markdown
## 3.4.3 非利息净收入

| 项目 | 2025年 | 2024年 | 增减额 | 增幅(%) |
|------|--------|--------|--------|---------|
| 手续费及佣金净收入 | 5,576 | 5,443 | 133 | 2.44 |
| 投资收益 | 20,073 | 15,700 | 4,373 | 27.85 |
| 公允价值变动损益 | -3,535 | 7,912 | -11,447 | -144.68 |
| 汇兑收益 | 370 | 770 | -400 | -51.95 |
```

### 0.5 PyMuPDF4LLM 作为轻量备选

对于**原生PDF**（非扫描件），PyMuPDF4LLM 可作为快速备选。环境中已有 PyMuPDF，只需额外安装一个轻量包：

```bash
pip install pymupdf4llm

# 使用
import pymupdf4llm
md_text = pymupdf4llm.to_markdown("年报.pdf")
```

**适用场景**：快速预览、简单表格。不适合精度要求高的财务数据提取。

### 0.6 已知限制与应对

| 限制 | 影响 | 应对 |
|------|------|------|
| 跨页表格不自动合并 | 利润表/资产负债表可能被拆成两段 | 后处理：检测连续表格 + 表头匹配合并 |
| 复杂嵌套表头 | 多级表头可能错位 | 结构化提取时用正则二次校准 |
| GPU 内存需求（8GB VRAM） | Apple Silicon 可能较慢 | 使用 pipeline 后端（CPU模式），牺牲速度保兼容 |
| AGPL-3.0 许可证 | 若做 SaaS 服务有合规要求 | 个人项目无影响；商用需评估 |

---

## 一、问题背景

### 1.1 案例复盘：华夏银行（600015）研报缺陷

将系统生成的华夏银行基本面研报与专业金融博主的财报拆解对比后，发现三个结构性盲区：

| 盲区 | 博主数据 | 我们的研报 | 影响 |
|------|---------|----------|------|
| **公允价值变动损益** | -35.35亿（同比-114.47亿），占利润272亿的42% | 完全未提及 | 严重低估2026年利润弹性 |
| **逾期贷款绝对值** | 逾期90天+ 281.83亿，重组113.70亿 | 承认"数据缺失" | 无法精算NPL率2 |
| **OCI与股东权益** | 其他综合收益-6.90亿（-114.45%），股东权益低于预期 | 完全未提及 | 未识别一次性扰动 |

### 1.2 根因分析

盲区并非"数据不存在"，而是**数据未进入分析管道**：

- 华夏银行2025年报txt文件（622KB，29926行）完整可用
- 公允价值变动损益在第1421行，逾期贷款在第2729行，重组贷款在第2787行
- 但这些数据既没有embedding进ChromaDB，也没有结构化提取到数据库

**当前数据流的断裂点：**

```
年报PDF (完整)
    |
    x--- 未转换 ---> Markdown (不存在)
    x--- 未embedding ---> ChromaDB (空)
    x--- 未结构化提取 ---> financial_balance / bank_asset_quality (仅AKShare数据)
    |
    v
data_tools.py 只能获取AKShare的汇总数据
    |
    v
Prompt → LLM → 缺少关键数据的研报
```

**目标数据流：**

```
年报PDF --[MinerU]--> Markdown
    |                    |
    |                    +---> [通路A] IngestPipeline → ChromaDB → RAG检索
    |                    |         (管理层讨论、风险披露、定性内容)
    |                    |
    |                    +---> [通路B] 正则提取 → MySQL → data_tools.py
    |                              (利润表、逾期贷款、OCI、现金流)
    |
    v
five_step.py ← 行业差异化Prompt ← 精确数字 + RAG段落
    |
    v
完整研报（含非息收入分析、一次性损益识别、NPL率2精算）
```

### 1.3 目标

打通年报原文到研报生成的完整数据通路，使系统能够：

1. **精确提取**年报中的关键财务数字（利润表拆分、逾期贷款、资本结构等）
2. **智能召回**年报原文段落作为RAG上下文（管理层讨论、风险披露等）
3. **自动检测**一次性损益项（公允价值波动、资产减值、营业外收支等）
4. **跨期对比**同一公司多年数据变化趋势

---

## 二、整体架构

### 2.1 双通路设计

```
年报PDF/TXT
    |
    +---> [通路A] Embedding入库 ---> ChromaDB ---> RAG检索
    |         (全文理解、管理层讨论、风险披露、定性分析)
    |
    +---> [通路B] 结构化提取 ---> MySQL ---> data_tools.py
              (精确数字、利润表、资产质量、资本结构)
              |
              v
          five_step.py → 行业差异化Prompt → LLM → 研报
```

**通路A（Embedding）**：解决"定性信息"的召回问题。管理层对业务的讨论、风险因素披露、行业展望等非结构化内容，通过RAG检索注入Prompt。

**通路B（结构化提取）**：解决"定量数据"的精确性问题。利润表科目、逾期贷款分类、资本充足率明细等数字，通过正则/模式匹配提取后写入数据库，由data_tools.py直接读取。

### 2.2 改造范围总览

| 模块 | 改造内容 | 优先级 | 复杂度 |
|------|---------|--------|--------|
| **ingest_pipeline** | 支持年报txt批量embedding | P0 | 低 |
| **annual_report_parser** | 新建：年报结构化提取器 | P0 | 中 |
| **financial_income表** | 补充非息收入拆分字段 | P0 | 低 |
| **bank_asset_quality表** | 补充逾期贷款绝对值 | P0 | 低 |
| **data_tools.py** | 新增利润表拆分/一次性损益方法 | P1 | 中 |
| **prompts.py** | Step1增加非息收入异常检测 | P1 | 低 |
| **行业适配** | 非银行年报提取模板 | P2 | 高 |

---

## 三、通路A：Embedding入库

### 3.1 目标

将年报原文embedding进ChromaDB的`reports` collection，使RAG检索能召回年报段落。

### 3.2 实现方案

**统一以 Markdown 为 embedding 源**。PDF 先通过 MinerU 转为 md，然后用现有 IngestPipeline 的 MarkdownParser 处理：

```
年报PDF --[MinerU]--> 年报.md --[IngestPipeline]--> ChromaDB
```

```python
from investment_rag.ingest.ingest_pipeline import IngestPipeline

pipeline = IngestPipeline()

# Markdown文件（MinerU转换产出）直接入库
result = pipeline.ingest_paths(
    ["/path/to/annual_reports/600015/md/"],
    collection="reports"
)
```

IngestPipeline 已原生支持 `.md` 文件，**无需修改解析逻辑**。MarkdownParser 按标题分节、自动提取 metadata，天然适合年报的章节结构。

### 3.3 优化考量

**3.3.1 为什么选 Markdown 而非 txt/pdf**

| 维度 | Markdown (MinerU) | TXT | PDF (PyMuPDF) |
|------|-------------------|-----|---------------|
| 表格结构 | `\| col \| col \|` 标准格式 | 逐行排列，无结构 | 可能错位 |
| 标题层级 | `##` `###` 原生 heading | 无（纯文本） | 无 |
| 分块质量 | MarkdownParser 按标题切分 | 需定制 parser | 按页切分 |
| 正则提取友好度 | 极高（表格格式统一） | 中（需状态机） | 低 |
| 已有 parser | MarkdownParser（已实现） | 需新增 | PDFParser（已实现） |
| 一份文件双用 | embedding + 结构化提取 | 仅 embedding | 仅 embedding |

**结论**：Markdown 是唯一能**同时服务通路A和通路B**的格式。

**3.3.2 分块策略优化**

当前设置（chunk_size=800, overlap=150）对年报场景偏小。年报中的财务表格和管理层讨论段落通常较长。

**建议**：
- 年报专用 chunk_size 提升到 1200-1500
- Markdown 的 `##` 标题是天然分段点，MarkdownParser 已支持按标题切分
- 表格区域（`| ... |` 连续行）整块保留，避免表格被拆到两个 chunk

**3.3.3 Metadata 增强**

当前 MarkdownParser 已支持 frontmatter metadata 提取。在 MinerU 转换后、embedding 前，为 md 文件添加 frontmatter：

```yaml
---
stock_code: "600015"
stock_name: "华夏银行"
report_year: 2025
report_type: "annual"
source: "华夏银行_600015_2025_年报"
---
```

可以写一个简单的预处理脚本，从文件名解析出 stock_code / stock_name / report_year / report_type，自动注入 frontmatter。MarkdownParser 会自动将这些字段作为每个 chunk 的 metadata，支持 ChromaDB 的精确过滤：

```python
# RAG 检索时按股票+年份过滤
hits = retriever.retrieve(
    query="公允价值变动损益",
    collection="reports",
    where={"stock_code": "600015", "report_year": 2025}
)
```

### 3.4 预期效果

embedding完成后，`query_rag_multi()` 将能召回如下内容：

```
查询: "华夏银行 公允价值变动损益"
→ 命中: "投资收益、公允价值变动损益、汇兑收益合计为169.08亿元，
         同比减少74.74亿元，下降30.65%..."

查询: "华夏银行 逾期贷款 重组贷款"
→ 命中: "逾期90天以上贷款余额281.83亿元...重组贷款账面余额113.70亿元..."
```

### 3.5 局限性

RAG检索能返回原文段落，但LLM需要从非结构化文本中理解数字关系。对于"公允价值变动从+79.12亿变成-35.35亿，摆动114.47亿"这种需要跨行计算的场景，纯RAG可能不够精确。因此**通路B（结构化提取）是必要补充**。

---

## 四、通路B：结构化数据提取

### 4.1 设计思路

年报txt文件格式高度规范（有`<!-- page N -->`标记、固定章节结构），适合用**正则+模式匹配**做结构化提取，而非依赖LLM。

核心思路：**按章节定位 → 按表格模式提取 → 校验后写入数据库**。

### 4.2 提取目标与优先级

#### P0：直接影响研报质量的数据

**4.2.1 利润表非息收入拆分**

| 提取字段 | 来源章节 | 示例数据（华夏银行2025） |
|---------|---------|----------------------|
| 手续费及佣金净收入 | 3.4.3 非利息净收入 | 55.76亿 |
| 投资收益 | 同上 | 200.73亿 |
| 公允价值变动损益 | 同上 | **-35.35亿** |
| 汇兑收益 | 同上 | 3.70亿 |
| 其他业务收入 | 同上 | 62.36亿 |
| 非息收入合计 | 同上 | 289.66亿 |

**提取方法**：定位"非利息净收入"或"非利息收入"章节标题，向下扫描表格行，匹配`科目名 金额 金额 增减额 增幅`的5列模式。

**4.2.2 逾期贷款分类绝对值（银行）**

| 提取字段 | 来源章节 | 示例数据 |
|---------|---------|---------|
| 逾期1-90天贷款 | 3.8.6 按逾期期限划分 | 132.44亿 |
| 逾期91-360天贷款 | 同上 | 162.34亿 |
| 逾期361天-3年贷款 | 同上 | 87.12亿 |
| 逾期3年以上贷款 | 同上 | 32.37亿 |
| **逾期90天以上合计** | 同上 | **281.83亿** |
| 重组贷款余额 | 3.8.7 重组贷款情况 | **113.70亿** |

**提取方法**：定位"逾期期限"或"逾期贷款"章节标题，解析固定格式表格。

**4.2.3 其他综合收益（OCI）**

| 提取字段 | 来源位置 | 示例数据 |
|---------|---------|---------|
| 其他综合收益变动 | 主要会计科目变动 | -6.90亿 (-114.45%) |
| 变动原因 | 同上 | 其他债权投资公允价值变动 |

#### P1：提升分析深度的数据

**4.2.4 利息收支结构（银行）**

| 提取字段 | 来源 | 用途 |
|---------|------|------|
| 生息资产平均余额 | 3.4.1/3.4.2 | 计算真实NIM |
| 各类贷款收益率 | 利息收入细分表 | 资产端定价能力 |
| 存款平均成本率 | 利息支出细分表 | 负债端成本优势 |
| 活期存款占比 | 存款结构表 | 低成本负债比例 |

**4.2.5 利润表完整拆分（通用）**

| 提取字段 | 用途 |
|---------|------|
| 营业收入 | 营收趋势 |
| 营业成本 | 毛利率计算 |
| 管理费用 / 销售费用 / 研发费用 | 三费分析 |
| 资产减值损失 | 一次性减值检测 |
| 营业外收支 | 非经常性损益剥离 |
| 归母净利润 | 核心盈利能力 |

**4.2.6 现金流量表关键项**

| 提取字段 | 用途 |
|---------|------|
| 经营活动现金流净额 | 盈利含金量 |
| 投资活动现金流净额 | 资本开支强度 |
| 筹资活动现金流净额 | 融资需求判断 |

#### P2：远期扩展

- 贷款行业分布与集中度（银行）
- 分部报告（多元化企业）
- 关联交易明细
- 或有事项与承诺

### 4.3 数据库Schema设计

#### 4.3.1 新增表：financial_income_detail（利润表明细）

```sql
CREATE TABLE IF NOT EXISTS financial_income_detail (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    -- 银行专用：利息收支
    interest_income DOUBLE COMMENT '利息收入(亿)',
    interest_expense DOUBLE COMMENT '利息支出(亿)',
    net_interest_income DOUBLE COMMENT '利息净收入(亿)',
    -- 非息收入拆分
    fee_commission_net DOUBLE COMMENT '手续费及佣金净收入(亿)',
    investment_income DOUBLE COMMENT '投资收益(亿)',
    fair_value_change DOUBLE COMMENT '公允价值变动损益(亿)',
    exchange_gain DOUBLE COMMENT '汇兑收益(亿)',
    other_business_income DOUBLE COMMENT '其他业务收入(亿)',
    non_interest_income_total DOUBLE COMMENT '非息收入合计(亿)',
    -- 通用利润表
    operating_revenue DOUBLE COMMENT '营业收入(亿)',
    operating_cost DOUBLE COMMENT '营业成本(亿)',
    selling_expense DOUBLE COMMENT '销售费用(亿)',
    admin_expense DOUBLE COMMENT '管理费用(亿)',
    rd_expense DOUBLE COMMENT '研发费用(亿)',
    finance_expense DOUBLE COMMENT '财务费用(亿)',
    asset_impairment DOUBLE COMMENT '资产减值损失(亿)',
    credit_impairment DOUBLE COMMENT '信用减值损失(亿)',
    non_operating_income DOUBLE COMMENT '营业外收入(亿)',
    non_operating_expense DOUBLE COMMENT '营业外支出(亿)',
    net_profit DOUBLE COMMENT '归母净利润(亿)',
    -- OCI
    other_comprehensive_income DOUBLE COMMENT '其他综合收益(亿)',
    total_comprehensive_income DOUBLE COMMENT '综合收益总额(亿)',
    -- 元数据
    source VARCHAR(20) DEFAULT 'annual_report' COMMENT '数据来源',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='利润表明细（年报提取）';
```

#### 4.3.2 扩展现有表：bank_asset_quality

```sql
-- 在现有 bank_asset_quality 表基础上补充字段
ALTER TABLE bank_asset_quality
    ADD COLUMN overdue_1_90 DOUBLE COMMENT '逾期1-90天贷款(亿)' AFTER overdue_91,
    ADD COLUMN overdue_91_360 DOUBLE COMMENT '逾期91-360天贷款(亿)' AFTER overdue_1_90,
    ADD COLUMN overdue_361_3y DOUBLE COMMENT '逾期361天-3年贷款(亿)' AFTER overdue_91_360,
    ADD COLUMN overdue_3y_plus DOUBLE COMMENT '逾期3年以上贷款(亿)' AFTER overdue_361_3y,
    ADD COLUMN overdue_90_npl_ratio DOUBLE COMMENT '逾期90天+/不良贷款比值' AFTER overdue_3y_plus,
    ADD COLUMN total_overdue DOUBLE COMMENT '逾期贷款总额(亿)' AFTER overdue_90_npl_ratio;
```

#### 4.3.3 新增表：financial_cashflow（现金流关键项）

```sql
CREATE TABLE IF NOT EXISTS financial_cashflow (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    operating_cashflow DOUBLE COMMENT '经营活动现金流净额(亿)',
    investing_cashflow DOUBLE COMMENT '投资活动现金流净额(亿)',
    financing_cashflow DOUBLE COMMENT '筹资活动现金流净额(亿)',
    source VARCHAR(20) DEFAULT 'annual_report',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COMMENT='现金流关键项（年报提取）';
```

### 4.4 年报解析器设计

#### 4.4.1 模块结构

```
data_analyst/
└── financial_fetcher/
    ├── annual_report_extractor.py       # 新增：年报结构化提取器（主入口）
    ├── extraction_templates/            # 新增：提取模板目录
    │   ├── base_template.py             # 基类：Markdown表格通用解析
    │   ├── bank_template.py             # 银行年报提取规则
    │   └── general_template.py          # 通用年报提取规则
    ├── md_converter.py                  # 新增：PDF→Markdown 转换封装（调用MinerU）
    └── storage.py                       # 已有：扩展save方法
```

放在 `data_analyst/financial_fetcher/` 下，与现有的 fetcher/storage 体系对齐。

#### 4.4.2 PDF→Markdown 转换封装

```python
class MDConverter:
    """封装 MinerU 的 PDF→Markdown 转换"""

    def convert(self, pdf_path: str, output_dir: str, lang: str = "ch") -> str:
        """转换单个PDF，返回md文件路径"""

    def batch_convert(self, pdf_dir: str, output_dir: str) -> List[str]:
        """批量转换目录下所有PDF"""

    def inject_frontmatter(self, md_path: str, stock_code: str, stock_name: str,
                           report_year: int, report_type: str):
        """为md文件注入YAML frontmatter（从文件名解析）"""
```

#### 4.4.3 结构化提取器核心逻辑

**基于 Markdown 表格提取**（比 txt 简单得多）：

```
AnnualReportExtractor
│
├── load(md_path) → 加载 Markdown 文件
│
├── locate_sections() → 按 ## 标题定位各章节
│   ├── "非利息净收入" / "非利息收入" → income_section
│   ├── "逾期期限" / "逾期贷款" → overdue_section
│   ├── "重组贷款" → restructured_section
│   ├── "现金流量" → cashflow_section
│   └── ...
│
├── parse_md_table(section_text) → 通用 Markdown 表格解析
│   ├── 识别 | col1 | col2 | ... | 格式
│   ├── 自动处理表头行和分隔行 (|---|---|)
│   ├── 返回 List[Dict]（每行一个 dict）
│   └── 数字清洗：去逗号、处理负号、单位转换
│
├── extract_income_detail() → 从利润表章节提取
│   ├── 调用 parse_md_table() 解析表格
│   ├── 按科目名映射到 schema 字段
│   └── 返回 dict
│
├── extract_overdue_loans() → 从逾期贷款章节提取
│
├── extract_restructured_loans() → 从重组贷款章节提取
│
├── extract_cashflow() → 从现金流量章节提取
│
├── extract_oci() → 从其他综合收益章节提取
│
├── validate(data) → 数据校验
│   ├── 非息收入各项加总 ≈ 合计值
│   ├── 逾期各档加总 ≈ 逾期总额
│   └── 数量级合理性检查
│
└── save(data) → 写入数据库
```

**关键优势**：Markdown 表格是标准格式（`| ... | ... |`），一个通用的 `parse_md_table()` 方法即可处理所有表格，不再需要 txt 的状态机解析。

#### 4.4.4 提取模板设计

银行年报和非银行年报的章节结构差异较大，采用模板模式：

```python
class BaseExtractionTemplate:
    """提取模板基类 - 通用 Markdown 表格解析"""
    def parse_md_table(self, text: str) -> List[Dict]: ...   # 通用表格解析
    def get_section_keywords(self) -> dict: ...               # 章节定位关键词
    def extract_income(self, section_text) -> dict: ...       # 利润表
    def extract_cashflow(self, section_text) -> dict: ...     # 现金流

class BankTemplate(BaseExtractionTemplate):
    """银行年报提取模板"""
    def extract_overdue_loans(self, text) -> dict: ...        # 逾期贷款分类
    def extract_restructured_loans(self, text) -> dict: ...   # 重组贷款
    def extract_nim_detail(self, text) -> dict: ...           # 净息差拆解
    def extract_deposit_structure(self, text) -> dict: ...    # 存款结构

class GeneralTemplate(BaseExtractionTemplate):
    """通用年报提取模板"""
    def extract_segment_revenue(self, text) -> dict: ...      # 分部收入
    def extract_rd_detail(self, text) -> dict: ...            # 研发费用
    def extract_inventory(self, text) -> dict: ...            # 存货周转
```

#### 4.4.5 Markdown 表格提取的优势（vs txt）

```
TXT 格式（当前）：                    Markdown 格式（MinerU 转换后）：
  项目                                | 项目 | 2025年 | 2024年 | 增减额 | 增幅(%) |
  2025 年                             |------|--------|--------|--------|---------|
  2024 年                             | 手续费及佣金净收入 | 5,576 | 5,443 | 133 | 2.44 |
  增减额                              | 投资收益 | 20,073 | 15,700 | 4,373 | 27.85 |
  增幅（%）                            | 公允价值变动损益 | -3,535 | 7,912 | -11,447 | -144.68 |
  手续费及佣金净收入
  5,576
  5,443
  133
  2.44
  投资收益
  20,073
  ...

  → 需要复杂状态机解析              → 一个正则即可：re.split(r'\s*\|\s*', line)
```

**简化程度**：Markdown 表格解析代码量约为 txt 状态机的 1/5。

### 4.5 data_tools.py 新增方法

```python
# 新增方法清单

def get_income_detail(self, stock_code: str, years: int = 3) -> str:
    """
    获取利润表明细（非息收入拆分）。
    数据源：financial_income_detail 表
    输出：格式化文本表格，含同比变动
    用途：Step1 注入，识别一次性损益项
    """

def get_non_recurring_items(self, stock_code: str) -> str:
    """
    检测一次性/非经常性损益项。
    逻辑：
      1. 公允价值变动损益同比变动超过净利润的20% → 标记
      2. 资产减值损失同比变动超过50% → 标记
      3. 营业外收支异常 → 标记
    输出：异常项列表 + 对净利润的影响金额
    用途：Step1 / Step3 注入
    """

def get_overdue_loan_detail(self, stock_code: str) -> str:
    """
    获取逾期贷款分类明细（银行专用）。
    数据源：bank_asset_quality 表（扩展后）
    输出：逾期各档金额/占比 + 同比趋势 + NPL率2计算
    用途：Step1 注入
    """

def get_cashflow_summary(self, stock_code: str, years: int = 3) -> str:
    """
    获取现金流关键指标。
    输出：经营/投资/筹资三大活动净额 + 经营现金流/净利润比值
    用途：Step1 / Step3 注入
    """
```

### 4.6 Prompt模板升级

#### Step1 银行专项关注新增

```
4. 非息收入异常波动检测
   - 公允价值变动损益同比变动幅度（若超过净利润20%须单独拆解）
   - 投资收益 vs 公允价值变动的方向是否背离（反映持有到期 vs 交易性策略差异）
   - 其他综合收益（OCI）变动及对净资产的影响

5. 一次性损益剥离
   - 剔除公允价值变动、资产处置损益、营业外收支后的"核心利润"
   - 核心利润增速 vs 报表净利润增速对比
   - 若两者背离超过5%，须明确指出哪个更能反映经营实质
```

#### Step3 估值偏差检测新增

```
估值分析须注意：
- 若当期存在大额一次性损益（公允价值变动、减值等），须基于"核心利润"而非报表利润估算合理PE/PB
- 一次性损益的回摆潜力：若当期因极端市场环境导致投资损失，下期回摆概率及对盈利弹性的影响
```

---

## 五、实施路径

### Phase 0：PDF→Markdown 转换基础设施（0.5天）

**目标**：建立 PDF→MD 的标准化转换流程

| 步骤 | 任务 | 产出 |
|------|------|------|
| 0.1 | 安装 MinerU：`pip install mineru` | 转换工具就绪 |
| 0.2 | 试跑华夏银行2025年报，验证表格转换质量 | 对比 md 表格 vs txt 原文，确认数字准确 |
| 0.3 | 实现 `md_converter.py` 封装（批量转换 + frontmatter 注入） | 标准化工具 |
| 0.4 | 批量转换28只股票的全部年报PDF | `/annual_reports/{code}/md/` 目录下的 md 文件 |

**验证点**：
```python
# 验证转换质量：华夏银行非息收入表格
with open("华夏银行_600015_2025_年报.md") as f:
    content = f.read()
assert "| 公允价值变动损益 |" in content  # 表格格式正确
assert "-3,535" in content or "-3535" in content  # 数字准确
```

### Phase 1：Embedding入库（1天）

**目标**：让 RAG 能"看到"年报内容

| 步骤 | 任务 | 产出 |
|------|------|------|
| 1.1 | 为 md 文件注入 frontmatter（stock_code, report_year 等） | metadata 增强 |
| 1.2 | 调整年报 chunk_size 到 1200-1500 | 更适合年报的分块参数 |
| 1.3 | 华夏银行 embedding 入库，验证 RAG 召回质量 | ChromaDB 中有年报 chunks |
| 1.4 | 全量 embedding：28只股票年报 md 全部入库 | 完整的年报知识库 |

**验证点**：
```python
# 验证RAG能召回年报内容
hits = retriever.retrieve("华夏银行 公允价值变动损益", collection="reports", top_k=3)
assert any("169.08" in h['text'] or "公允价值" in h['text'] for h in hits)
```

### Phase 2：结构化提取-银行专项（2-3天）

**目标**：精确提取银行年报的关键财务数字

| 步骤 | 任务 | 产出 |
|------|------|------|
| 2.1 | 创建 `financial_income_detail` 表 | DDL + migration |
| 2.2 | 扩展 `bank_asset_quality` 表字段 | ALTER TABLE |
| 2.3 | 实现 BankTemplate 提取器 | 利润表拆分 + 逾期贷款 + OCI |
| 2.4 | 华夏银行验证：提取2023-2025三年数据 | 数据入库 + 交叉验证 |
| 2.5 | 其他银行验证（601288农行、601398工行等如有年报） | 模板适配度验证 |

**验证点**：
```python
# 验证结构化数据
row = db.query("SELECT fair_value_change FROM financial_income_detail WHERE stock_code='600015' AND report_date='2025-12-31'")
assert row.fair_value_change == -35.35  # 与博主数据一致
```

### Phase 3：研报管道集成（1-2天）

**目标**：新数据源接入五步法分析管道

| 步骤 | 任务 | 产出 |
|------|------|------|
| 3.1 | data_tools.py 新增4个方法 | get_income_detail等 |
| 3.2 | 更新BANK_CONFIG和Prompt模板 | 非息收入检测 + 一次性损益剥离 |
| 3.3 | five_step.py 条件注入新数据 | Step1/Step3增强 |
| 3.4 | 重跑华夏银行研报，对比改进效果 | 对比报告 |

**验证点**：
- 重新生成的华夏银行研报应能识别114亿公允价值变动冲击
- Step1应包含"核心利润 vs 报表利润"对比
- Step3应提示2026年投资收益回摆的利润弹性

### Phase 4：通用化扩展（3-5天）

**目标**：支持非银行行业年报提取

| 步骤 | 任务 | 产出 |
|------|------|------|
| 4.1 | 实现 GeneralTemplate | 营收/毛利/三费/现金流提取 |
| 4.2 | 行业适配：制造业、消费、科技 | 分部收入、研发费用等 |
| 4.3 | 自动化批量提取脚本 | CLI命令：extract --code 600015 |
| 4.4 | 数据质量监控 | 提取率、异常值检测 |

### Phase 5：持续运维（长期）

| 任务 | 频率 | 说明 |
|------|------|------|
| 新年报入库 | 每季度 | 季报/半年报/年报发布后自动触发 |
| 提取模板维护 | 按需 | 年报格式变化时调整正则 |
| 数据校验 | 每次提取后 | 自动对比AKShare数据，标记差异 |

---

## 六、关键技术决策

### 6.1 统一中间格式：Markdown

**决策：PDF→Markdown（MinerU）→ 双通路**

理由：
- Markdown 表格格式标准化（`| col | col |`），正则提取极简
- 一份 md 文件同时服务 Embedding（通路A）和结构化提取（通路B）
- MinerU 对中文财报的表格识别精度最高（OmniDocBench 90.67）
- 所有28只股票都有 PDF，md 可统一生成，不依赖 txt 是否存在
- IngestPipeline 已有 MarkdownParser，无需新增解析器

**txt 文件定位**：作为转换质量的交叉校验基准（华夏银行有 txt 可对比），不作为主数据源。

### 6.2 正则提取 vs LLM提取

**决策：正则为主，LLM为辅**

| 方案 | 准确率 | 速度 | 成本 | 适用场景 |
|------|--------|------|------|---------|
| 正则/模式匹配 | 高（结构化表格） | 极快 | 零 | 固定格式的财务表格 |
| LLM提取 | 中-高（依赖prompt） | 慢 | 高 | 非结构化段落中的隐含数据 |
| 混合 | 最高 | 中 | 中 | 正则提取后LLM校验/补充 |

**策略**：
- P0数据（利润表、逾期贷款等固定表格）→ 纯正则
- P1数据（管理层讨论中的定性判断）→ RAG+LLM
- 校验环节 → LLM辅助检查提取结果的合理性

### 6.3 存储粒度：按年报 vs 按季报

**决策：年报+半年报优先，季报按需**

理由：
- 年报信息最完整（逾期贷款分类、分部报告等仅年报/半年报披露）
- 季报通常只有利润表和资产负债表摘要，细节不足
- 存储空间和提取成本线性增长，先保证质量再扩量

### 6.4 数据一致性：年报提取 vs AKShare

两个来源可能存在数据差异（口径、四舍五入、合并/母公司差异）。

**处理策略**：
- 以年报原文为"金标准"，AKShare作为快速获取渠道
- 同一字段两个来源都有时，年报提取值覆盖AKShare值
- 新增`source`字段标记数据来源
- 提取后自动对比，差异超过阈值（如5%）生成告警

---

## 七、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|------|------|------|------|
| txt文件格式不一致（不同券商排版差异） | 中 | 提取规则失效 | 多家公司样本测试，抽象出通用模式 |
| 年报表格跨页/合并单元格 | 中 | 数字提取遗漏 | 状态机解析 + 跨页合并逻辑 |
| 单位不统一（百万/亿/千元） | 低 | 数量级错误 | 单位检测 + 自动转换 + 数量级校验 |
| 新年度年报格式变化 | 低 | 需调整模板 | 版本化模板 + 格式变化检测 |
| embedding质量影响RAG召回 | 中 | 关键段落未命中 | 调大chunk_size + metadata过滤 + query改写 |

---

## 八、预期收益

### 8.1 研报质量提升

以华夏银行为例，改进前后对比：

| 分析维度 | 改进前 | 改进后 |
|---------|--------|--------|
| 非息收入分析 | 完全缺失 | 投资收益/公允价值/手续费三维拆解 |
| 一次性损益识别 | 无 | 自动检测并量化影响（如-114亿） |
| NPL率2精算 | "数据缺失"告退 | 逾期90天+281.83亿 + 重组113.70亿 → 1.541% |
| 盈利弹性预测 | "增速5.5%" | "核心利润增速X% + 公允价值回摆Y亿 = 实际弹性Z%" |
| OCI影响 | 未提及 | "其他综合收益-6.9亿侵蚀净资产，一次性因素" |

### 8.2 覆盖范围

| 维度 | 当前 | 目标 |
|------|------|------|
| 可分析股票 | 全A股（AKShare汇总数据） | 28只重点持仓（年报深度数据） |
| 银行分析深度 | NIM + NPL率 + 资本充足率 | + 利润表拆分 + 逾期分类 + 存款结构 + OCI |
| 非银行分析深度 | 营收/利润/ROE | + 三费拆分 + 现金流 + 分部收入 + 一次性损益 |

### 8.3 自动化程度

```
当前：
  年报PDF → 人工阅读 → 脑中分析

目标：
  年报PDF/TXT → 自动embedding + 结构化提取 → 数据库 → 五步法分析 → 研报
```

---

## 附录

### A. 华夏银行年报txt关键位置索引

| 数据 | 行号 | 章节 |
|------|------|------|
| 净息差 | 3933-3934 | 3.14.2 净息差 |
| 手续费及佣金净收入 | 1411-1415 | 3.4.3 非利息净收入 |
| 投资收益 | 1416-1420 | 同上 |
| 公允价值变动损益 | 1421-1425 | 同上 |
| 非息收入合计 | 1446-1449 | 同上 |
| 投资收益+公允价值+汇兑 合计 | 1512-1513 | 3.4.3.2 |
| 其他综合收益 | 2217-2219 | 主要会计科目变动 |
| 逾期贷款分布 | 2729-2786 | 3.8.6 按逾期期限划分 |
| 重组贷款 | 2787-2802 | 3.8.7 重组贷款情况 |

### B. 当前数据表字段覆盖图

```
financial_balance (现有)
├── total_assets         ✓ AKShare
├── total_equity         ✓ AKShare
├── loan_total           ✓ AKShare
├── npl_ratio            ✓ AKShare
├── provision_coverage   ✓ AKShare
├── cap_adequacy_ratio   ✓ AKShare
├── tier1_ratio          ✓ AKShare
└── nim                  ✓ AKShare

bank_asset_quality (现有，待补充)
├── overdue_91           x 需从年报提取
├── restructured         x 需从年报提取
├── npl_ratio2           x 需计算
├── provision_adj        ✓ AKShare
└── profit_adj_est       ✓ AKShare

financial_income_detail (待新建)
├── fair_value_change    x 需从年报提取
├── investment_income    x 需从年报提取
├── fee_commission_net   x 需从年报提取
├── credit_impairment    x 需从年报提取
├── other_comp_income    x 需从年报提取
└── ...

financial_cashflow (待新建)
├── operating_cashflow   x 需从年报提取
├── investing_cashflow   x 需从年报提取
└── financing_cashflow   x 需从年报提取
```

### C. 已有年报文件清单（28只股票）

```
000408  000786  000792  000807  000933
002241  002318  002738  002895  02899
300199  300274  300760  300775
600015  600027  600406  600863  600938  600989
601155  601225  601288  601318  601398  601857
605090  688386
```

---

*文档版本: v1.0 | 2026-04-08*
