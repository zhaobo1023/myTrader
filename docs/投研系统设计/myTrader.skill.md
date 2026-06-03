---
type: note
title: "stock-report 已经出现在 skill 列表中。完成。"
domain: Personal
read_status: read
---

stock-report 已经出现在 skill 列表中。完成。

---

skill 已创建：/Users/zhaobo/.claude/skills/sto ck-report/SKILL.md

使用方式：

/stock-report 601567 三星医疗               # 全部三份（默认）
/stock-report 601567 三星医疗 --reports tech
    # 只生成技术扫描
/stock-report 601567 三星医疗 --reports tech,fundamental  # 技术 + 五步法

Skill 做什么：

1. 解析 code / name / reports 参数
2. 并行后台执行选中的模块命令
3. 各模块完成后，提取 body 内容（HTML/Markdown 转 HTML）
4. 用统一的页眉 + 锚点导航合并为单一 HTML 文件，输出到 output/rag/reports/{code}_{name}_
{date}_full.html
5. open 自动在浏览器中打开

三个模块对应关系：

| 标识 | 分析维度 | 输出目 |
| --- | --- | --- |
|  |  | 录 |
|  | 技术面扫描 | output/ |  | tech | v2.0（K线/均线/MACD/R | single_ |
|  | SI/KDJ/量价） | scan/ |
|  | 五截面分析（技术/资金 | output/ |  | five | /基本面/情绪/资本周期 | researc |
|  | 综合评分） | h/ |
| fund | 五步法基本面（财报/护 | output/ |  | amen | 城河/估值/催化剂/风险 | rag/rep |
| tal | 操作建议） | orts/ |
