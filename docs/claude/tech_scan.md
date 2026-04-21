# 持仓技术面扫描

新增于 2026-03-30，每日盘后自动扫描持仓股票的技术面状态，生成 Markdown 报告。

## 核心特性

- 持仓解析 - 自动解析 Markdown 持仓文件，提取 A 股/ETF 代码
- 技术指标 - MA5/20/60/250、MACD、RSI、成交量比
- 信号检测 - 回踩/突破、金叉/死叉、超买/超卖、RPS 走弱
- 分级预警 - [RED]红灯/[WARN]黄灯/[OK]绿灯 三级预警
- Backlog - 自动记录数据缺失、计算失败等异常

## 模块结构

```
strategist/tech_scan/
├── config.py              # 扫描配置
├── portfolio_parser.py    # 持仓文件解析
├── data_fetcher.py        # 数据库数据获取
├── indicator_calculator.py # 技术指标计算
├── signal_detector.py     # 信号检测逻辑
├── report_generator.py    # Markdown 报告生成
├── backlog_manager.py     # 异常记录管理
├── scheduler.py           # 定时调度
└── run_scan.py            # 主入口
```

## 快速开始

```bash
# 手动执行扫描
python -m strategist.tech_scan.run_scan

# 指定日期扫描
python -m strategist.tech_scan.run_scan --date 2026-03-29

# 启动定时调度（每日 16:30）
python -m strategist.tech_scan.scheduler

# 立即执行一次
python -m strategist.tech_scan.scheduler --run-now
```

## 输出结果

- `/Users/zhaobo/Documents/notes/Finance/TechScanEveryDay/TechScan_YYYYMMDD.md` - 扫描报告
- `/Users/zhaobo/Documents/notes/Finance/TechScanEveryDay/backlog.md` - 异常记录
- `output/tech_scan/scan_YYYYMMDD.log` - 执行日志

## 配置

- 持仓文件: `/Users/zhaobo/Documents/notes/Finance/Positions/00-Current-Portfolio-Audit.md`
- 数据库环境: `online` (使用线上 MySQL)

详见 `docs/technical_scan_design.md`

[返回主文档](../../CLAUDE.md)
