# EEDP Nexus

首次在另一台电脑使用，请看 [快速上手](docs/GETTING-STARTED.md)：克隆后执行 `install-agent.cmd`，WSL Agent 使用 `install-agent.cmd -Wsl`。脚本自动识别路径，注册 MCP 和 Skill，新开 Agent 会话即可发现工具。
Agent 入口为根目录 [SKILL.md](SKILL.md)，顶层 AGENTS.md 会引导 Agent 读取它：首次使用发现缺少注册时自动初始化，已接入时跳过安装并使用组件 Skill。

参与项目开发的 Agent 可按需读取 [项目目录 Skill](skills/eedp-nexus-layout/SKILL.md) 和 [组件开发 Skill](skills/eedp-nexus-component-development/SKILL.md)；组件契约以标准手册为准。

Windows 免安装程序：`release/EEDP-Nexus-v0.5.0/EEDP Nexus.exe`；发布 ZIP：`release/EEDP-Nexus-v0.5.0-win64.zip`。
分发包：`release/EEDP Nexus-0.5.0-win64.zip`。保留完整目录，内置 Python、Tk、串口依赖与本机烧录引擎。
桌面入口已改为“EEDP Nexus”；Agent 使用 `EEDP-Agent.exe mcp` 或 CLI，WSL 使用随包提供的桥接脚本。

重新构建：使用 Python 3.12 创建 `.packaging-venv`，安装 `build-requirements.txt`，运行 `tools/build_app.py`。
`tools/check-packaged.py` 使用隔离状态和回环设备验证 exe，不触碰物理串口。

这是 Windows 与 WSL Agent 共用的本机能力工作台，不内置大模型或自动决策循环。
核心服务位于 Windows，MCP / CLI 对外暴露能力，桌面界面负责状态展示和管理。
使用说明由 `skills/use-agent-workbench/` 提供；Agent 发现组件后按需调用，不依赖界面点击。

四项设计要求：统一深色界面；Agent 接口优先；使用说明技能化；插件标准化、设置持久化、通信日志共享。

双路视频工作区可预览已准备的 MJPEG 与 H.264 素材；预览由双路组件内置播放器实现，不再提供独立视频组件。发送与预览独立，关闭预览不会停止视频流。

在活动栏组件图标上点击右键，可打开“高级操作”，按公开接口调用该组件的其他动作；表单支持滚动和素材文件选择。双路视频改选素材后，“预览”显示当前选择，只有重新准备并启动发送后板卡画面才会随之改变。已选择的素材与成功启动的板卡地址会记忆，发送状态以工作区连接信息为准。


0.5.0 增加 SLogic Combo8 插件及波形工作区：原始电平、活动包络、时间轴、缩放、平移、游标、离线 UART/I²C/SPI 解码与 VCD/CSV 导出。用户和 Agent 使用相同状态及文件；未知信号电压不得开始采集。可用“示例波形”查看人工生成的 UART 示例，界面明确标注非设备实采。
右侧活动栏按启用组件动态显示；组件管理和 Agent 配置内嵌并复用页面。日志切换不展示从头滚到尾的过程。
组件规范的权威入口为 [COMPONENT-STANDARD.md](COMPONENT-STANDARD.md)，串口、烧录、逻辑分析均已迁移至 schema 1.1。运行 `python check-components.py` 可在不接触硬件的条件下检查契约；打包自动执行校验。

串口发送区可保存、载入和删除命名常用命令；选择预设仅载入，需手动发送。左侧发送设置的命令行模式和 HEX 发送互斥。文本结尾支持 CRLF、CR、LF、NONE；HEX 按输入字节发送，不追加结尾。
串口端口列表附带系统报告的设备描述，如 CH340；连接仍使用对应的 COM 端口号。
数据波形组件可绘制现有串口接收的多条数值曲线；设备逐行输出 `@plot voltage=3.3,temp=25`。格式与命名规则见 [组件说明](plugins/plot/README.md)。

### 外观与按钮文字

右侧“设置 → 外观”提供六套即时切换的配色：Nexus 深空、Mocha 柔紫、Nord 极地、暖砂日落、Paper 明亮、高对比黑金。Mocha/Nord 参考其公开调色板并按工作台用途调整：[Catppuccin](https://catppuccin.com/palette/)、[Nord](https://www.nordtheme.com/docs/colors-and-palettes/)。
按钮字体、8–14 号字号、加粗、图标显示可分别设置，提供预览和恢复默认，自动记忆；仅文字模式保留功能名称。Agent 连接配置在同一设置页的另一个标签中。
操作按钮支持圆角/直角、舒适/紧凑，按字号和文字适配尺寸，具有悬停、按下和键盘焦点反馈；发送按钮保持自然高度。串口波特率提供 35 个预设（110–12000000，含 96000），也可直接输入正整数；最终由设备和驱动决定可用速率。
启动时提供约 1 秒的几何图形点亮过渡，可点击跳过，也可在外观设置关闭。使用主线程定时绘制，不阻塞后台，不显示虚假初始化百分比。
侧栏使用 [Lucide](https://lucide.dev/icons) 的固定版本 0.468.0 SVG，附带 ISC 许可证，按主题生成 24/28/32/40 原生尺寸图标，默认 32px。工作区外框与标题固定，上方文件/视图/设备/工具/帮助菜单均连接实际功能。Agent 桥接状态位于底部，可点击查看后台及设备占用。
高对比方案对主要文字、按钮及边界执行计算对比度测试，以 [WCAG 对比度说明](https://www.w3.org/WAI/WCAG22/Understanding/contrast-enhanced) 为设计参考，不宣称完整软件认证。
主题通过 `nexus_ui/themes.py` 统一管理，供现有和未来组件继承，不改变采集、串口、烧录或后台服务。

MCU 多功能控制器仅在 component-plans/ 预留，当前不实现、不连接硬件、不暴露可调用动作。自动化开发及工具板的分阶段方向见 [单片机自动化开发路线](docs/MCU-AUTOMATION-PLAN.md)：先用现成工具开发手头的 STM32F407，再逐步扩展为可由 Agent 控制的硬件节点。

## 结构

### 日志中心（0.5.0）

顶部“日志中心”统一查询持久历史，支持本地日期（YYYY-MM-DD）、插件、事件类型和调用来源筛选，按时间倒序分页；不再依赖窗口内存中的最近 500 条调用记录。

所有日志统一位于安装目录 `.state/logs/`：在线事件库与轮换 JSONL、`diagnostics/` 诊断、`flash-<任务>/` 烧录附件、`archives/` 历史归档、`exports/` 导出 ZIP。

默认在线保留 30 天、约 10 万条，淘汰前先写入压缩 JSONL 归档；归档保留期 90 天，总容量目标 512 MB。历史与固件默认保护，不会自动删除；运行中及最近烧录、在线数据库和导出包也不自动删除。因此容量目标为尽力执行，保护数据超限会明确提示。取消保护后，后台每小时按期限及容量清理未保护归档；可手动执行维护。

导出 ZIP 中在线事件应用当前筛选；诊断、已完成烧录及归档烧录附件不筛选，固件默认排除。导出包保留在本地并复制到用户所选位置。ZIP 不包含接口令牌或设置。更早归档事件可从归档目录读取 JSONL.gz，目前不支持在在线列表中检索压缩归档。

Agent 使用 `logs.query`、`logs.inventory`、`logs.export`、`logs.policy`、`logs.maintain` RPC，或对应的 `workbench_logs_*` MCP 工具。日志策略经校验持久化，不能用通用 settings.update 绕过校验。

- `nexus_core/core.py`：组件注册、动作描述、串口资源所有权、活动记录；根目录 `core.py` 保留插件兼容入口。
- `plugins/serial/`：可单独启停、移除的串口组件。
- `plugins/beken/`：可单独启停、移除的 Beken 烧录组件。
- `nexus_core/plugin_manager.py`：扫描插件清单、检查 API 版本、管理生命周期。
- `nexus_core/settings.py`：共享设置的原子保存与读取。
- `nexus_core/api.py`：统一服务操作；CLI、桌面、MCP 使用同一接口。
- `mcp-bridge.py`：兼容已有 Agent 配置的 MCP 入口。
- `agent_bridge/`：MCP 协议、Windows / WSL 桥接和 Agent 安装逻辑。
- `run-workbench.py`：本地服务与 Agent CLI。
- `nexus_ui/desktop.py`：桌面客户端，各组件使用独立操作布局，通过相同组件接口执行动作。

组件互不导入、互不调用。新组件只需提供 `plugin.json`、入口类的动作方法、
`status()` 和 `close()`，放进 `plugins/` 后扫描即可，无需修改核心注册代码。
接口描述中包含参数类型、默认值，以及破坏性操作标记。
完整插件契约见 [PLUGIN-API.md](docs/PLUGIN-API.md)。

## 目录

```text
EEDP-Nexus/
├── run-workbench.py / workbench.cmd   服务、CLI 与启动入口
├── nexus_ui/                         桌面客户端、工作区与外观
├── core.py                           插件公共接口兼容入口
├── nexus_core/                       核心服务、API、设置与插件管理
├── mcp-bridge.py                     Agent MCP 兼容入口
├── agent_bridge/                     Agent 接入、MCP 与 Windows/WSL 桥接
├── docs/                             使用说明、协议与开发规划
├── plugins/                          可拆卸组件包
│   ├── serial/                       plugin.json + component.py
│   ├── beken/                        固件烧录
│   ├── slogic/                       逻辑分析
│   └── netvideo/                     双路视频与预览
├── skills/use-agent-workbench/       Agent 使用技能与 CLI 辅助脚本
├── integrations/                     两端 MCP / Codex 配置
├── tests/                            组件、界面与平台验证
├── tools/                            资源生成及开发检查脚本
├── build/ / dist/ / release/         构建中间文件、构建输出与发布包
├── .state/                           共享设置、事件库、日志与任务快照
└── .venv/                            独立运行环境
```

`components/` 仅保留旧导入路径的兼容层，核心服务不依赖它。

## 启动

本机已配置独立 Python 环境及 pyserial。双击桌面的“EEDP Nexus”或运行：

```powershell
.\workbench.cmd gui
.\workbench.cmd tools
.\workbench.cmd status
.\workbench.cmd call serial.ports
```

没有 Python 的新电脑需要安装支持 tkinter 的 Python，再运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Agent 调用

工作台技能源位于 `skills/use-agent-workbench/`，已安装到 Windows 和 WSL 的用户级
`~/.agents/skills/use-agent-workbench`。可以在 Codex 中提及 `$use-agent-workbench`。
其中的 `scripts/workbench-client.py` 根据环境调用同一 Windows 服务，并处理 Linux 固件交接。

`tools` 返回所有组件和动作的结构化描述。推荐使用 UTF-8 JSON 参数文件：

```powershell
# connect.json: {"port":"COM14","baudrate":1500000}
.\workbench.cmd call serial.connect --args-file connect.json
# send.json: {"text":"video tf","newline":"CRLF"}
.\workbench.cmd call serial.send --args-file send.json
.\workbench.cmd events --component serial --watch
.\workbench.cmd call serial.disconnect
.\workbench.cmd call beken.inspect
# 使用预检后的参数启动烧录；CLI 调用本身就是授权，不会再次弹框。
.\workbench.cmd call beken.start
.\workbench.cmd call beken.status
.\workbench.cmd stop
```

串口和烧录是独立能力。Agent 编排示例：
检查串口状态 → 保存所需连接参数 → 断开串口 → 预检固件 → 启动烧录 →
轮询结果 → 根据结果决定是否恢复串口监控。
工作台不会擅自断开其他组件，也不会因进入烧录页自动操作设备。

MCP 配置分别见 `integrations/windows.codex.toml`、`integrations/wsl.codex.toml`；
通用 MCP 客户端使用同目录的 `.mcp.json` 示例。原生工具包括 `workbench_status`、
`workbench_plugins`、`workbench_events`、`serial__connect`、`beken__start` 等。
服务端依插件启停更新工具列表，MCP 会发送目录变化通知。
底层管理操作也可通过 `workbench.cmd rpc <method> --args-file <file>` 调用。

## 后台与日志

- GUI 默认不连接设备、不发送数据；关闭 GUI 不会停止后台服务。
- “停止后台服务”或 `stop` 释放串口；烧录运行时拒绝停止整个服务。
- 日志位于工作台目录下的 `.state\logs`，不修改系统安全策略或目录权限。
- `.state/settings.json` 共享保存界面布局、串口参数、烧录设置和插件启停状态；设置不会自动执行命令。
- `.state/logs/activity.sqlite3` 为 Windows / WSL / 桌面共用的可查询事件库，保留最近 100,000 条事件；
  事件 ID 跨服务重启递增，并记录调用来源标签。原有活动日志会导入索引。
- `activity.jsonl` 包含带时间戳的调用、RX/TX 和烧录输出，在线保留六份约 10 MB 的轮换日志，更旧文本先移入归档。
  RX/TX 包含 Base64 原始字节，文本按增量解码保留跨包字符。
- 每次烧录另存固件快照、SHA-256 和引擎日志，防止构建工具中途覆盖源固件。
  旧烧录任务会按在线保留期移入归档；运行中及最近任务保留原位置，历史记录和固件可分别保护。
- 服务仅监听本机回环地址，每次启动随机端口及访问令牌，令牌保存在当前用户的状态目录。
  不向局域网开放；不是远程多用户服务。

## 烧录边界

当前烧录适配器针对本机已验证的 CH340 / BK7236 命令流程，默认 COM14、1500000、起始地址 0。
不是所有芯片通用的烧录器；不提供 Efuse、OTP、SecureBoot 或全片擦除动作。
采用目标区间写入，长度按 256 字节向上对齐，未对齐末尾处理由厂商引擎执行。
按回车符实时解析原厂引擎的擦除 / 写入阶段百分比；连接阶段显示等待状态，进度条不移动。
GUI 写入前确认；Agent CLI `beken.start` 会直接执行。中止或超时可能需要重新烧录。

外部调试助手和 BKFIL 不属于本工作台资源管理范围；如果占用串口，系统会报告打开失败。
打开串口可能引起 USB 转串口驱动切换控制线，取决于硬件连接。

## 验证

运行自动检查：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -p "test_*.py" -v
```

2026-11-10 已完成组件 / 界面 / 插件 / 共享状态测试，以及 COM14 / BK7236 真实烧录。
更新固件 3,547,900 字节，SHA-256 为
`27a2db355e7bb9fa0d067a4d60cac1af4da3c59d8b0de8d943de52551f98cec9`。
本机引擎成功时退出码为 1，因此成功判定同时要求本次独立日志中出现
`WriteFlash ->pass`、`Writing Flash OK` 和 `All Finished Successfully`。
已验证窗口关闭 / 重开不影响任务，烧录后资源释放，串口能重新连接并收发换行 / 提示符。

Receive display: at most 20 refreshes/sec, bounded batches and a 100,000-character view cache. Repeated NUL bytes are condensed; long lines are split. Overload skips old display entries with a notice. Raw backend events remain unchanged; pause only pauses display.

双路视频发送组件 netvideo：离线预处理MJPEG/H.264，再向板卡TCP 5001/5002分别发送；转码或容器解复用需要显式提供可信FFmpeg路径，符合格式的原始 MJPEG 可直接校验。支持停止、重连、循环与H.264滑动限流，详见[组件说明](plugins/netvideo/README.md)及[协议责任文档](docs/NETVIDEO-PROTOCOL.md)。板卡和手机曾完成短时联调，长期稳定性取决于网络及素材。

视频工作区同时显示本地与远程状态，支持一键播放两路、单路播放和停止、素材预览；高级参数默认收起。可快速切换预生成的 MJPEG 30、40、45、50、55、60 KiB 单帧上限。先选择本组 `*-mjpeg-<档位>k-1024x608-12fps.mjpeg` 文件并填写板卡 IP；原始 MJPEG 档位无需 FFmpeg。按钮只停止并重新准备、启动 MJPEG，H.264 不受操作影响。目标档位文件缺失时不会停止当前播放；切换会从目标文件开头播放，不代表网络能够稳定承载所有档位。界面速率为发送端计数，非板卡接收率。
