---
name: eedp-nexus-layout
description: Navigate or reorganize the EEDP Nexus source repository while preserving application entry points, imports, builds, and Agent integration.
---

# EEDP Nexus 项目目录

在 EEDP Nexus 仓库中定位代码或调整目录时使用。先阅读仓库根目录的 `AGENTS.md` 和 `README.md`，以当前文件及引用为准。

- 根目录：运行、安装和兼容入口；`core.py` 与 `mcp-bridge.py` 保留既有插件和 Agent 配置的兼容接口。
- `nexus_core/`：核心服务、插件管理、API 与设置；`app_paths.py` 决定源码模式下的根路径。
- `nexus_ui/`：桌面窗口、工作区、外观和界面辅助模块；`agent_bridge/`：Agent 安装和 MCP 桥接；`docs/`：使用文档；`tools/`：构建及检查脚本；`tests/`：自动化测试。
- `plugins/`：独立组件及清单；`components/`：既有组件实现；`skills/`：Agent 技能；`assets/`：运行资源；`vendor/`：随包依赖。
- `build/`、`dist/`、`release/` 为构建和交付目录，`.state/` 存放运行状态，均不应当作普通源码清理。`.private-cloud-backup/` 是用户备份，不处理。

调整路径前搜索 Python 导入、动态加载、脚本路径、打包规格和文档引用；保持现有安装指针、运行目录及 Agent 接口可用。变更后运行相应自动测试及 `python check-components.py`，涉及分发时在隔离输出目录验证打包。自动检查不得操作物理硬件。
