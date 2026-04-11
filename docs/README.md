# myTrader 文档中心

欢迎来到 myTrader 项目文档中心！

## 🚀 快速开始

**📖 查看完整索引:** [docs/index.md](index.md)

**🎯 按角色查找文档:**
- 👨‍💻 **量化策略研究员** → 查看[策略类文档](#策略类文档)
- 🔧 **后端开发工程师** → 查看[系统设计类文档](#系统设计类文档)
- 🛠️ **运维工程师** → 查看[部署运维类文档](#部署运维类文档)
- 🎨 **前端开发工程师** → 查看[实施计划](plans/)

---

## 📂 文档分类

### 策略类文档
量化交易策略的设计、实现与回测

- [微盘策略迭代总结](microcap_iteration_summary.md) - v1.0-v1.4版本迭代记录
- [微盘策略集合](microcap_strategy_collection.md) - 6种微盘因子策略
- [微盘回测增强](microcap_backtest_enhancement.md) - 7项回测增强
- [陶博士策略](doctor_tao_strategy.md) - RPS+动量选股
- [乖离率策略设计](log_bias_strategy_design.md) - 对数偏差均值回归
- [因子验证报告](factor_validation_report.md) - 因子有效性测试

### 系统设计类文档
系统架构、技术方案和功能设计

- [myTrader技术方案](myTrader_tech_plan.md) - 完整技术方案
- [任务调度系统设计](myTrader_scheduler_design.md) - DAG任务管理
- [投研RAG系统](MinerU_markdown_investment_rag_spec_2039278797563613184.md) - 检索增强生成
- [五截面分析框架](投研系统_五截面分析框架设计.md) - 五维度分析
- [资本周期报告系统](资本周期报告系统_设计方案.md) - 资本周期研报
- [研报引擎演进方案](report_engine_evolution_plan.md) - 引擎升级方案

### 部署运维类文档
生产环境部署、安全配置和运维

- [部署安全指南](deployment_security_guide.md) - 安全配置完整指南
- [生产环境部署指南](deployment_guide.md) - ECS部署流程
- [SSH密钥配置](SSH_KEY_SETUP.md) - SSH配置指南
- [IP访问指南](ip_access_guide.md) - 访问配置指南

### 数据库类文档
数据库连接、双写改造和数据管理

- [双写改造指南](dual_write_guide.md) - Dual-Write技术改造
- [数据库连接说明](database_connection_guide.md) - 双环境配置
- [Windows双写数据](windows_dual_write_data.md) - Windows环境配置

### 开发工具类文档
CI/CD、测试流程和开发工具

- [CI/CD方案总结](CI_CD_SUMMARY.md) - 持续集成/部署
- [测试流程指南](testing-flow-guide.md) - 测试规范
- [技术扫描设计](technical_scan_design.md) - 持仓扫描系统
- [Skill Gateway指南](skill-gateway-guide.md) - 技能网关使用

### Claude工具类文档
Claude CLI安装配置和使用

- [Claude CLI安装配置](CLAUDE_CLI_SETUP.md) - ECS安装指南
- [Claude快速参考](CLAUDE_QUICK_REFERENCE.md) - GLM-5快速参考

---

## 📅 详细实施计划

按日期组织的详细实施计划位于 `plans/` 目录：

- **2026-04-07**: [五截面框架v2](plans/2026-04-07-five-section-framework-v2.md)
- **2026-04-06**: [监控提醒系统](plans/2026-04-06-watchlist-scan-notify.md)
- **2026-04-05**: [RBAC权限系统](plans/2026-04-05-rbac-permissions.md)
- **2026-04-02**: [财务数据获取器](plans/2026-04-02-financial-fetcher-impl.md)
- **2026-03-29**: [SVD市场监控](plans/2026-03-29-svd-market-monitor-design.md)

> 📋 查看完整实施计划: [plans/](plans/)

---

## 🔍 热门文档

### 🌟 最新文档
1. [微盘策略迭代总结](microcap_iteration_summary.md) *(2026-04-11)*
2. [部署安全指南](deployment_security_guide.md) *(2026-04-11)*
3. [微盘策略集合](microcap_strategy_collection.md) *(2026-04-10)*

### 📈 必读文档
1. [myTrader技术方案](myTrader_tech_plan.md) - 了解系统全貌
2. [数据库连接说明](database_connection_guide.md) - 配置数据库环境
3. [生产环境部署指南](deployment_guide.md) - 部署到生产环境

---

## 📊 文档统计

- **文档总数**: 53 篇
- **总大小**: ~966KB
- **主要类别**: 9 大类
- **实施计划**: 17 篇

详见: [完整文档索引](index.md#-文档统计)

---

## 📝 文档使用指南

### 如何查找文档？

1. **按角色**: 在上述分类中找到你的角色，查看推荐文档
2. **按主题**: 使用浏览器的查找功能（Ctrl+F）搜索关键词
3. **按日期**: 查看 [plans/](plans/) 目录中的实施计划

### 如何贡献文档？

1. 遵循[文档命名规范](index.md#-文档规范)
2. 使用统一的[文档模板](index.md#-文档模板)
3. 更新本文档索引

---

## 🔗 快速链接

- **项目主文档**: [CLAUDE.md](../CLAUDE.md)
- **API文档**: `/api/docs`
- **测试报告**: `/tests/reports`
- **部署日志**: `/var/log/myTrader/`

---

**维护者**: zhaobo
**最后更新**: 2026-04-11

有问题或建议？欢迎反馈！
