# myTrader 项目文档索引

**更新时间:** 2026-04-11
**维护者:** zhaobo
**文档总数:** 50+ 篇

---

## 📚 文档分类导航

### 1️⃣ 策略类文档
量化交易策略的设计、实现与回测文档。

| 文档 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| [微盘策略迭代总结](microcap_iteration_summary.md) | 微盘策略v1.0-v1.4版本迭代记录，包含每次改进的方向、改动内容和产出结果 | 2026-04-11 | 20KB |
| [微盘策略集合](microcap_strategy_collection.md) | 6种微盘因子策略完整文档（PEG/PE/ROE/EBIT/PEG_EBIT_MV/Pure MV） | 2026-04-10 | 33KB |
| [微盘回测增强](microcap_backtest_enhancement.md) | 7项回测增强技术方案（PIT规则/涨跌停/流动性/基准/退市/滑点） | 2026-04-10 | 15KB |
| [陶博士策略](doctor_tao_strategy.md) | RPS+动量选股策略，基于相对强度指标的趋势跟踪策略 | 2026-04-08 | 21KB |
| [乖离率策略设计](log_bias_strategy_design.md) | 基于对数偏差的均值回归策略设计文档 | 2026-04-08 | 15KB |
| [因子验证报告](factor_validation_report.md) | 因子有效性验证测试报告（2026-03-24） | 2026-04-08 | 14KB |

---

### 2️⃣ 系统设计类文档
系统架构、技术方案和功能设计文档。

| 文档 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| [myTrader技术方案](myTrader_tech_plan.md) | 个人投研平台完整技术方案与任务拆解 | 2026-04-08 | 21KB |
| [任务调度系统设计](myTrader_scheduler_design.md) | 统一任务调度器技术方案，YAML DAG任务依赖管理 | 2026-04-08 | 38KB |
| [投研RAG系统](MinerU_markdown_investment_rag_spec_2039278797563613184.md) | 投研检索增强生成系统技术方案 | 2026-04-08 | 18KB |
| [五截面分析框架](投研系统_五截面分析框架设计.md) | 投研系统五维度分析框架设计 | 2026-04-08 | 18KB |
| [资本周期报告系统](资本周期报告系统_设计方案.md) | 基于资本周期的研报生成系统设计 | 2026-04-08 | 19KB |
| [研报引擎演进方案](report_engine_evolution_plan.md) | 研报引擎行业差异化+数据源升级方案 | 2026-04-08 | 16KB |

---

### 3️⃣ 部署运维类文档
生产环境部署、安全配置和运维指南。

| 文档 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| [部署安全指南](deployment_security_guide.md) | 生产环境部署方案与安全配置完整指南 | 2026-04-11 | 11KB |
| [生产环境部署指南](deployment_guide.md) | ECS生产环境完整部署流程 | 2026-04-09 | 9KB |
| [ECS部署指南](DEPLOYMENT_ECS.md) | systemd+Nginx部署方案 | 2026-04-08 | 9KB |
| [ECS快速启动](QUICK_START_ECS.md) | 5分钟快速部署参考 | 2026-04-08 | 4KB |
| [SSH密钥配置](SSH_KEY_SETUP.md) | ECS SSH密钥配置指南 | 2026-04-09 | 7KB |
| [Git配置验证](ECS_GIT_VERIFICATION.md) | ECS Git SSH配置验证清单 | 2026-04-09 | 5KB |
| [IP访问指南](ip_access_guide.md) | IP+Port访问方式配置指南 | 2026-04-11 | 3KB |

---

### 4️⃣ 数据库类文档
数据库连接、双写改造和数据补充方案。

| 文档 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| [双写改造指南](dual_write_guide.md) | Dual-Write双写技术改造完整指南 | 2026-04-10 | 16KB |
| [数据库连接说明](database_connection_guide.md) | myTrader双环境数据库配置说明 | 2026-04-10 | 5KB |
| [Windows双写数据](windows_dual_write_data.md) | Windows环境双写数据配置指南 | 2026-04-10 | 10KB |
| [数据补充方案](data_supplement_guide.md) | 数据源补充与数据完善方案 | 2026-04-08 | 6KB |

---

### 5️⃣ 开发工具类文档
CI/CD、测试流程和开发工具使用指南。

| 文档 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| [CI/CD方案总结](CI_CD_SUMMARY.md) | 持续集成/部署方案与流程 | 2026-04-08 | 12KB |
| [测试流程指南](testing-flow-guide.md) | 测试流程与规范 | 2026-04-08 | 9KB |
| [技术扫描设计](technical_scan_design.md) | 持仓技术面扫描系统设计 | 2026-04-08 | 9KB |
| [技术扫描PRD](technical_scan_prd.md) | 持仓技术面扫描产品需求文档 | 2026-04-08 | 4KB |
| [Skill Gateway指南](skill-gateway-guide.md) | 技能网关使用指南 | 2026-04-08 | 10KB |

---

### 6️⃣ 实施进度类文档
项目各阶段完成总结和状态报告。

| 文档 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| [Phase 1-3完成总结](IMPLEMENTATION_COMPLETE.md) | 研报引擎第一阶段实施完成总结 | 2026-04-08 | 11KB |
| [研报引擎演进总结](PHASE123_SUMMARY.md) | 研报引擎Phase 1-3完成总结 | 2026-04-08 | 8KB |
| [技能/API同步状态](SKILL_API_SYNC_STATUS.md) | 技能/API同步状态报告（2026-04-08） | 2026-04-08 | 7KB |

---

### 7️⃣ Claude工具类文档
Claude CLI安装配置和使用指南。

| 文档 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| [Claude CLI安装配置](CLAUDE_CLI_SETUP.md) | Claude CLI在ECS (CentOS)上的安装和配置 | 2026-04-08 | 13KB |
| [Claude快速参考](CLAUDE_QUICK_REFERENCE.md) | Claude CLI + GLM-5快速参考 | 2026-04-08 | 8KB |

---

### 8️⃣ 其他文档
年报提取、任务清单和产品需求。

| 文档 | 说明 | 最后更新 | 大小 |
|------|------|----------|------|
| [年报数据提取方案](annual_report_extraction_plan.md) | 年报数据提取与研报增强方案 | 2026-04-09 | 35KB |
| [任务清单](task.md) | 项目任务清单 | 2026-04-08 | 5KB |
| [产品需求文档](prd.md) | 产品需求文档 | 2026-04-08 | 2KB |

---

### 9️⃣ 详细实施计划 (plans/)
按日期组织的详细实施计划文档，位于 `plans/` 子目录。

#### 2026-04-07
- [五截面框架v2](plans/2026-04-07-five-section-framework-v2.md) - 五截面分析框架第二版

#### 2026-04-06
- [监控提醒系统](plans/2026-04-06-watchlist-scan-notify.md) - 监控列表扫描与通知系统
- [技能网关](plans/2026-04-06-skill-gateway.md) - Skill Gateway技能网关设计
- [行情概览面板](plans/2026-04-06-market-overview-dashboard.md) - 市场概览看板设计

#### 2026-04-05
- [RBAC权限系统](plans/2026-04-05-rbac-permissions.md) - 基于角色的访问控制
- [日志系统](plans/2026-04-05-logging-system.md) - 结构化日志系统设计
- [智能研报生成](plans/2026-04-05-intelligent-research-report.md) - 智能研报生成系统
- [五截面框架](plans/2026-04-05-five-section-framework.md) - 五截面分析框架
- [资本周期集成](plans/2026-04-05-capital-cycle-integration.md) - 资本周期系统集成

#### 2026-04-03
- [技术扫描v2实现](plans/2026-04-03-tech-scan-v2-impl.md) - 技术面扫描系统v2实现

#### 2026-04-02
- [多因子选股设计](plans/2026-04-02-multi-factor-selector-design.md) - 多因子选股器设计
- [财务数据获取器](plans/2026-04-02-financial-fetcher-impl.md) - 财务数据获取器实现
- [财务获取器设计](plans/2026-04-02-financial-fetcher-design.md) - 财务数据获取器设计

#### 2026-04-01
- [乖离率策略实现](plans/2026-04-01-log-bias-strategy-impl.md) - 乖离率策略实现方案

#### 2026-03-29
- [SVD市场监控实现](plans/2026-03-29-svd-market-monitor-impl.md) - SVD市场状态监控实现
- [SVD市场监控设计](plans/2026-03-29-svd-market-monitor-design.md) - SVD市场状态监控设计

---

## 📊 文档统计

| 类别 | 文档数量 | 总大小 |
|------|----------|--------|
| 策略类 | 6 | ~118KB |
| 系统设计类 | 6 | ~130KB |
| 部署运维类 | 7 | ~48KB |
| 数据库类 | 4 | ~37KB |
| 开发工具类 | 5 | ~44KB |
| 实施进度类 | 3 | ~26KB |
| Claude工具类 | 2 | ~21KB |
| 其他 | 3 | ~42KB |
| 详细实施计划 | 17 | ~500KB |
| **合计** | **53** | **~966KB** |

---

## 🔍 快速查找

### 按角色查找

**量化策略研究员**
- [微盘策略集合](microcap_strategy_collection.md)
- [陶博士策略](doctor_tao_strategy.md)
- [乖离率策略设计](log_bias_strategy_design.md)
- [因子验证报告](factor_validation_report.md)

**后端开发工程师**
- [myTrader技术方案](myTrader_tech_plan.md)
- [任务调度系统设计](myTrader_scheduler_design.md)
- [数据库连接说明](database_connection_guide.md)
- [双写改造指南](dual_write_guide.md)

**运维工程师**
- [部署安全指南](deployment_security_guide.md)
- [生产环境部署指南](deployment_guide.md)
- [SSH密钥配置](SSH_KEY_SETUP.md)
- [CI/CD方案总结](CI_CD_SUMMARY.md)

**前端开发工程师**
- [行情概览面板](plans/2026-04-06-market-overview-dashboard.md)
- [五截面框架](plans/2026-04-05-five-section-framework.md)

### 按主题查找

**回测系统**
- [微盘回测增强](microcap_backtest_enhancement.md)
- [微盘策略迭代总结](microcap_iteration_summary.md)
- [因子验证报告](factor_validation_report.md)

**数据管理**
- [数据库连接说明](database_connection_guide.md)
- [双写改造指南](dual_write_guide.md)
- [数据补充方案](data_supplement_guide.md)

**研报生成**
- [投研RAG系统](MinerU_markdown_investment_rag_spec_2039278797563613184.md)
- [五截面分析框架](投研系统_五截面分析框架设计.md)
- [资本周期报告系统](资本周期报告系统_设计方案.md)
- [研报引擎演进方案](report_engine_evolution_plan.md)

**市场监控**
- [SVD市场监控设计](plans/2026-03-29-svd-market-monitor-design.md)
- [技术扫描设计](technical_scan_design.md)
- [监控提醒系统](plans/2026-04-06-watchlist-scan-notify.md)

---

## 📅 最近更新

### 2026-04-11
- ✨ 新增 [微盘策略迭代总结](microcap_iteration_summary.md)
- ✨ 新增 [部署安全指南](deployment_security_guide.md)
- ✨ 新增 [IP访问指南](ip_access_guide.md)

### 2026-04-10
- 🔧 更新 [微盘策略集合](microcap_strategy_collection.md)
- 🔧 更新 [双写改造指南](dual_write_guide.md)
- 🔧 更新 [数据库连接说明](database_connection_guide.md)

### 2026-04-09
- ✨ 新增 [年报数据提取方案](annual_report_extraction_plan.md)
- ✨ 新增 [SSH密钥配置](SSH_KEY_SETUP.md)
- ✨ 新增 [Git配置验证](ECS_GIT_VERIFICATION.md)

---

## 📝 文档规范

### 文档命名规范
- 英文文档：使用小写字母和下划线，如 `microcap_strategy_collection.md`
- 中文文档：使用中文命名，如 `投研系统_五截面分析框架设计.md`
- 实施计划：使用日期前缀，如 `2026-04-05-logging-system.md`

### 文档模板
```markdown
# 文档标题

**文档版本:** v1.0
**更新时间:** YYYY-MM-DD
**维护者:** 作者名

---

## 一、概述
简要说明文档目的和内容

## 二、主要内容
详细内容...

## 三、总结
总结性内容
```

---

## 🔗 相关链接

- **代码仓库**: [GitHub](https://github.com/your-repo)
- **API文档**: `/api/docs`
- **测试报告**: `/tests/reports`
- **部署日志**: `/var/log/myTrader/`

---

**文档维护:** 如有文档问题或建议，请联系项目维护者。

**最后更新:** 2026-04-11
