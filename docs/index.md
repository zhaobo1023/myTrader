# myTrader 项目文档索引

**更新时间:** 2026-04-15
**维护者:** zhaobo
**文档总数:** 63 篇

---

## 文档分类导航

### 1. 估值数据增强 -- 最新

对标理杏仁竞品调研，补全数据层核心差距（指数估值分位/宏观数据/估值温度）。

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [理杏仁竞品调研](lixinger_research.md) | 产品功能/数据覆盖/可借鉴方向完整分析 | 2026-04-15 | 8KB |
| [估值增强技术方案](plans/2026-04-15-valuation-enhancement.md) | M1-M3 三里程碑，15 项任务清单 | 2026-04-15 | 10KB |

---

### 2. 策略模拟池 (SimPool)

SimPool 系统设计、任务拆解、Celery 自动化。

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [SimPool 系统设计](sim_pool_design.md) | 模拟池系统完整设计 (PoolManager/PositionTracker/NavCalculator/ReportGenerator) | 2026-04-14 | 16KB |
| [SimPool 任务拆解](sim_pool_tasks.md) | 28 项任务清单与实施记录 (T1.1-T5.6) | 2026-04-14 | 23KB |
| [小程序技术方案](mini-app-design.md) | 微信小程序 uni-app (Vue 3) 技术方案 | 2026-04-15 | 14KB |
| [调度器配置](scheduler_config.md) | YAML DAG 任务定义 (含 SimPool 定时任务) | 2026-04-14 | 5KB |

---

### 2. 财报分析系统

财报数据提取、银行评分卡、研报引擎的核心文档。

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [财报分析系统演进总结](financial_report_system_summary.md) | Phase 0-4 完整迭代记录、Qwen/Claude/f大对比分析、经验教训 | 2026-04-13 | 30KB |
| [年报数据提取方案](annual_report_extraction_plan.md) | PDF->MD->正则+LLM 提取的双路径架构设计 | 2026-04-08 | 34KB |
| [研报引擎演进方案](report_engine_evolution_plan.md) | 研报引擎行业差异化+数据源升级路线图 (Phase 1-4) | 2026-04-08 | 15KB |
| [研报引擎 Phase 1-3 总结](PHASE123_SUMMARY.md) | 行业路由/数据源接入/银行深度打磨三阶段完成总结 | 2026-04-08 | 7KB |
| [实施完成总结](IMPLEMENTATION_COMPLETE.md) | Phase 1-3 实施完成验证清单 | 2026-04-08 | 10KB |
| [One-Pager 变更日志](one_pager_changelog.md) | 研报 One-Pager 格式变更记录 | 2026-04-13 | 7KB |

---

### 3. 量化策略

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [微盘策略迭代总结](microcap_iteration_summary.md) | 微盘策略 v1.0-v1.4 迭代记录 | 2026-04-11 | 19KB |
| [微盘策略集合](microcap_strategy_collection.md) | 6 种微盘因子策略 (PEG/PE/ROE/EBIT/PEG_EBIT_MV/Pure MV) | 2026-04-10 | 32KB |
| [微盘 v3 回测总结](microcap_reports/v3_summary_20240101_20260410.md) | v3.0 全量回测报告 | 2026-04-13 | 5KB |
| [微盘回测增强](microcap_backtest_enhancement.md) | 7 项回测增强 (PIT/涨跌停/流动性/基准/退市/滑点) | 2026-04-10 | 14KB |
| [陶博士策略](doctor_tao_strategy.md) | RPS+动量选股策略 | 2026-03-25 | 20KB |
| [乖离率策略设计](log_bias_strategy_design.md) | 基于对数偏差的均值回归策略 | 2026-04-01 | 14KB |
| [因子验证报告](factor_validation_report.md) | 因子有效性验证测试 (2026-03-24) | 2026-03-24 | 14KB |

---

### 4. 系统架构设计

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [myTrader 技术方案](myTrader_tech_plan.md) | 个人投研平台完整技术方案与任务拆解 (28 项任务) | 2026-04-05 | 20KB |
| [任务调度系统设计](myTrader_scheduler_design.md) | YAML DAG 任务依赖管理调度器 | 2026-04-05 | 37KB |
| [市场看板设计](market_dashboard_design.md) | 市场概览看板页面设计与数据流 | 2026-04-14 | 27KB |
| [投研 RAG 系统](MinerU_markdown_investment_rag_spec_2039278797563613184.md) | 检索增强生成系统技术方案 | 2026-04-01 | 17KB |
| [五截面分析框架](投研系统_五截面分析框架设计.md) | 技术/资金流/基本面/舆情/资本周期五维框架 | 2026-04-05 | 17KB |
| [资本周期报告系统](资本周期报告系统_设计方案.md) | 基于资本周期的研报生成系统 | 2026-04-05 | 18KB |

---

### 5. 舆情监控系统

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [舆情监控集成方案](sentiment_monitoring_integration_plan.md) | VIX/新闻情感/事件检测/Polymarket 完整方案 | 2026-04-11 | 45KB |
| [舆情集成总结](SENTIMENT_INTEGRATION_SUMMARY.md) | 舆情模块集成完成总结 | 2026-04-11 | 12KB |
| [舆情数据需求](sentiment_data_requirements.md) | 舆情监控数据源和字段需求 | 2026-04-11 | 9KB |
| [舆情部署指南](sentiment_deployment_guide.md) | 舆情模块部署配置 | 2026-04-11 | 7KB |
| [舆情测试报告](sentiment_test_report.md) | 舆情模块测试结果 | 2026-04-11 | 5KB |

---

### 6. 部署运维

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [部署安全指南](deployment_security_guide.md) | 生产环境安全配置完整指南 | 2026-04-11 | 10KB |
| [生产环境部署指南](deployment_guide.md) | ECS 完整部署流程 | 2026-04-09 | 8KB |
| [ECS 部署指南](DEPLOYMENT_ECS.md) | systemd+Nginx 部署方案 | 2026-04-08 | 8KB |
| [ECS 快速启动](QUICK_START_ECS.md) | 5 分钟快速部署参考 | 2026-04-08 | 4KB |
| [ECS 部署检查清单](ECS_DEPLOYMENT_CHECKLIST.md) | 部署后验证清单 | 2026-04-11 | 5KB |
| [SSH 密钥配置](SSH_KEY_SETUP.md) | ECS SSH 密钥配置指南 | 2026-04-08 | 7KB |
| [Git 配置验证](ECS_GIT_VERIFICATION.md) | ECS Git SSH 配置验证 | 2026-04-08 | 5KB |
| [IP 访问指南](ip_access_guide.md) | IP+Port 访问配置 | 2026-04-11 | 2KB |
| [故障排查](troubleshooting.md) | 常见问题排查指南 | 2026-04-14 | 10KB |

---

### 7. 数据库

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [双写改造指南](dual_write_guide.md) | Dual-Write 双写技术改造 | 2026-04-10 | 15KB |
| [数据库连接说明](database_connection_guide.md) | 双环境数据库配置 | 2026-04-10 | 4KB |
| [Windows 双写数据](windows_dual_write_data.md) | Windows 环境双写配置 | 2026-04-10 | 10KB |
| [数据补充方案](data_supplement_guide.md) | 数据源补充与完善 | 2026-04-07 | 6KB |

---

### 8. 开发工具与流程

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [CI/CD 方案总结](CI_CD_SUMMARY.md) | 持续集成/部署方案 | 2026-04-08 | 11KB |
| [测试流程指南](testing-flow-guide.md) | 测试流程与规范 | 2026-04-05 | 8KB |
| [技术扫描设计](technical_scan_design.md) | 持仓技术面扫描系统 | 2026-03-30 | 9KB |
| [技术扫描 PRD](technical_scan_prd.md) | 持仓扫描产品需求 | 2026-03-30 | 3KB |
| [Skill Gateway 指南](skill-gateway-guide.md) | 技能网关使用指南 | 2026-04-06 | 9KB |
| [技能/API 同步状态](SKILL_API_SYNC_STATUS.md) | 同步状态报告 | 2026-04-08 | 6KB |

---

### 9. Claude CLI

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [Claude CLI 安装配置](CLAUDE_CLI_SETUP.md) | Claude CLI 在 ECS (CentOS) 上的安装 | 2026-04-08 | 12KB |
| [Claude 快速参考](CLAUDE_QUICK_REFERENCE.md) | Claude CLI 快速参考 | 2026-04-08 | 8KB |

---

### 10. 其他

| 文档 | 说明 | 更新 | 大小 |
|------|------|------|------|
| [综合技术文档](total_technical.md) | 技术栈综合参考 | 2026-04-13 | 6KB |
| [任务清单](task.md) | 项目任务清单 | 2026-03-24 | 5KB |
| [产品需求文档](prd.md) | 产品需求 | 2026-03-24 | 2KB |
| [每日开发日志](daily_dev_log.md) | 日常开发记录 | 持续更新 | 19KB |

---

## 详细实施计划 (plans/)

按日期组织的详细实施计划文档。

| 日期 | 文档 | 说明 | 大小 |
|------|------|------|------|
| 2026-04-07 | [五截面框架 v2](plans/2026-04-07-five-section-framework-v2.md) | 分析框架第二版优化 | 43KB |
| 2026-04-06 | [行情概览面板](plans/2026-04-06-market-overview-dashboard.md) | 市场概览看板设计 | 69KB |
| 2026-04-06 | [监控提醒系统](plans/2026-04-06-watchlist-scan-notify.md) | 监控列表扫描与通知 | 43KB |
| 2026-04-06 | [技能网关](plans/2026-04-06-skill-gateway.md) | Skill Gateway 设计 | 37KB |
| 2026-04-05 | [智能研报生成](plans/2026-04-05-intelligent-research-report.md) | 智能研报系统实现 | 67KB |
| 2026-04-05 | [五截面框架](plans/2026-04-05-five-section-framework.md) | 五截面分析框架实现 | 82KB |
| 2026-04-05 | [RBAC 权限系统](plans/2026-04-05-rbac-permissions.md) | 角色权限控制 | 35KB |
| 2026-04-05 | [资本周期集成](plans/2026-04-05-capital-cycle-integration.md) | 资本周期量化集成 | 28KB |
| 2026-04-05 | [日志系统](plans/2026-04-05-logging-system.md) | 结构化日志 | 22KB |
| 2026-04-03 | [技术扫描 v2](plans/2026-04-03-tech-scan-v2-impl.md) | 技术面扫描 v2 实现 | 32KB |
| 2026-04-02 | [财务数据获取器](plans/2026-04-02-financial-fetcher-impl.md) | 财务获取器详细实现 | 39KB |
| 2026-04-02 | [财务获取器设计](plans/2026-04-02-financial-fetcher-design.md) | 财务获取器架构设计 | 2KB |
| 2026-04-02 | [多因子选股设计](plans/2026-04-02-multi-factor-selector-design.md) | 多因子选股器 | 2KB |
| 2026-04-01 | [乖离率策略实现](plans/2026-04-01-log-bias-strategy-impl.md) | 乖离率策略实现 | 37KB |
| 2026-03-29 | [SVD 市场监控实现](plans/2026-03-29-svd-market-monitor-impl.md) | SVD 监控详细实现 | 49KB |
| 2026-03-29 | [SVD 市场监控设计](plans/2026-03-29-svd-market-monitor-design.md) | SVD 监控设计 | 8KB |

---

## 快速查找

### 按角色

**量化策略研究员**
- [微盘策略集合](microcap_strategy_collection.md)
- [陶博士策略](doctor_tao_strategy.md)
- [乖离率策略设计](log_bias_strategy_design.md)
- [因子验证报告](factor_validation_report.md)
- [财报分析系统总结](financial_report_system_summary.md)

**后端开发工程师**
- [myTrader 技术方案](myTrader_tech_plan.md)
- [任务调度系统设计](myTrader_scheduler_design.md)
- [SimPool 系统设计](sim_pool_design.md)
- [数据库连接说明](database_connection_guide.md)
- [双写改造指南](dual_write_guide.md)
- [年报数据提取方案](annual_report_extraction_plan.md)

**前端开发工程师**
- [市场看板设计](market_dashboard_design.md)
- [小程序技术方案](mini-app-design.md)
- [调度器配置](scheduler_config.md)

**运维工程师**
- [部署安全指南](deployment_security_guide.md)
- [生产环境部署指南](deployment_guide.md)
- [故障排查](troubleshooting.md)
- [CI/CD 方案总结](CI_CD_SUMMARY.md)

### 按主题

**SimPool 模拟池**
- [SimPool 系统设计](sim_pool_design.md) -- 完整架构设计
- [SimPool 任务拆解](sim_pool_tasks.md) -- 28 项实施任务
- [小程序技术方案](mini-app-design.md) -- 微信小程序方案

**财报分析 / 研报生成**
- [财报分析系统总结](financial_report_system_summary.md) -- 迭代全景 + 对比分析
- [年报数据提取方案](annual_report_extraction_plan.md) -- PDF->MD->DB 设计
- [研报引擎演进方案](report_engine_evolution_plan.md) -- 行业差异化路线图
- [投研 RAG 系统](MinerU_markdown_investment_rag_spec_2039278797563613184.md) -- RAG 检索
- [五截面分析框架](投研系统_五截面分析框架设计.md) -- 五维分析框架
- [资本周期报告系统](资本周期报告系统_设计方案.md) -- 资本周期

**量化策略 / 回测**
- [微盘策略集合](microcap_strategy_collection.md)
- [微盘回测增强](microcap_backtest_enhancement.md)
- [微盘策略迭代总结](microcap_iteration_summary.md)
- [因子验证报告](factor_validation_report.md)

**市场监控 / 舆情**
- [舆情监控集成方案](sentiment_monitoring_integration_plan.md)
- [SVD 市场监控设计](plans/2026-03-29-svd-market-monitor-design.md)
- [技术扫描设计](technical_scan_design.md)

**数据管理**
- [数据库连接说明](database_connection_guide.md)
- [双写改造指南](dual_write_guide.md)
- [数据补充方案](data_supplement_guide.md)

---

## 文档统计

| 类别 | 数量 | 总大小 |
|------|------|--------|
| 策略模拟池 (SimPool) | 4 | ~58KB |
| 财报分析系统 | 6 | ~103KB |
| 量化策略 | 7 | ~118KB |
| 系统架构设计 | 6 | ~136KB |
| 舆情监控系统 | 5 | ~78KB |
| 部署运维 | 9 | ~59KB |
| 数据库 | 4 | ~35KB |
| 开发工具与流程 | 6 | ~47KB |
| Claude CLI | 2 | ~20KB |
| 其他 | 4 | ~32KB |
| 估值数据增强 | 2 | ~18KB |
| 详细实施计划 (plans/) | 17 | ~563KB |
| **合计** | **72** | **~1267KB** |

---

## 文档规范

- 英文文档：小写字母+下划线，如 `microcap_strategy_collection.md`
- 中文文档：中文命名，如 `投研系统_五截面分析框架设计.md`
- 实施计划：日期前缀，如 `2026-04-05-logging-system.md`
- 禁止使用 emoji (MySQL utf8 不兼容)

---

**最后更新:** 2026-04-15（新增：理杏仁竞品调研 + 估值增强方案）
