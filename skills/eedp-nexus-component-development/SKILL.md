---
name: eedp-nexus-component-development
description: Develop or update EEDP Nexus components and their Agent interfaces using the project's component contract and hardware-free validation.
---

# EEDP Nexus 组件开发

新增、修改或迁移 EEDP Nexus 组件时使用。先读仓库根目录的 `AGENTS.md` 和 [组件开发标准手册](../../COMPONENT-STANDARD.md)；手册是契约的唯一权威来源，发生变化时以手册为准。

1. 查看目标组件的 `plugins/<id>/plugin.json`、实现、README、相关界面、测试和 `skills/use-agent-workbench/SKILL.md`，确认真实接口与状态。
2. 按手册保持组件独立、动作描述准确、设置和日志共享、资源占用与生命周期正确；Windows/WSL 通过同一后台访问硬件。
3. 同步实现、清单、文档、使用 Skill、手册及必要测试。修改通用规范时迁移并验证受影响的既有组件。
4. 提交或打包前从项目根目录运行 `python check-components.py` 和相关测试。测试、安装及打包不得自动采样、发送或烧录；硬件验证单独依据用户授权进行。

不要把计划中的组件写成已有能力；设备状态和实际安装位置应在操作时重新确认。
