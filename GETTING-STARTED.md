# EEDP Nexus：给另一台电脑使用

## 让 Agent 自动接入

让 Agent 打开本仓库并读取根目录 `SKILL.md`（顶层 `AGENTS.md` 已指向它）。
它会先检查已有 MCP/安装指针，缺失时运行下方初始化入口，已有接入则跳过，随后读取组件 Skill。
根目录 SKILL.md 本身不是各类 Agent 都会自动发现的通用机制；不读取 AGENTS.md 的客户端需显式让它读取该文件。

## 直接使用（推荐给使用者）

下载 Release 的 `EEDP-Nexus-v0.5.0-win64.zip`，解压并保留完整目录。
双击 `EEDP Nexus.exe` 使用界面；无需安装 Python。
双击 `install-agent.cmd` 注册当前 Windows 用户的 Codex MCP 和 Skill。
如果 Agent 在 WSL，使用 `install-agent.cmd -Wsl`，为默认发行版的当前用户同时注册。
WSL 需要 Python 3.9+、Windows interop；安装器内置 MIT 授权的 Tomli 兼容解析器，无需额外 pip 安装。设备和驱动仍在 Windows。
多个 WSL 发行版可在每个发行版中运行安装目录的 `python3 setup-agent.py`。

## 克隆源码（给开发者）

```powershell
git clone <你的仓库地址> EEDP-Nexus
cd EEDP-Nexus
.\install-agent.cmd -Wsl
```

不使用 WSL 时省略 `-Wsl`。Windows 需预装带 tkinter 的 Python 3.12+；脚本创建 `.venv` 并安装 requirements.txt。
初始化会识别实际克隆目录，写入当前用户安装指针、安装 Skill、更新 Codex 的 agent-workbench MCP 项并备份改动文件。
其他已有 MCP、模型设置保持不变；然后新开 Agent 会话。
可让 Agent “使用 EEDP Nexus 列出组件和串口”，确认它发现工具；这不自动打开串口。

源码含 SLogic 厂商工具及其出处记录；Beken 引擎需按其授权自行放到 `plugins/beken/bin/bk_loader.exe`，
或设置 `EEDP_BEKEN_ENGINE`。缺少该引擎只限制烧录，不妨碍串口和 Agent 接入。
设备驱动仍需用户电脑具备；初始化不会安装 USB 驱动、登录 Agent 账号或更改硬件状态。

## 配置位置与其他 Agent

- 安装指针：`~/.eedp-agent.json`。
- Skill：`~/.agents/skills/use-agent-workbench/`。
- Codex MCP：`$CODEX_HOME/config.toml` 或默认 `~/.codex/config.toml`。
- 通用 MCP JSON：软件目录 `.state/agent-config/mcp.json`（Windows）或 `mcp-wsl.json`（WSL），其他支持 stdio MCP 的 Agent 可导入对应文件。

各客户端配置格式不同，通用 JSON 不代表已经自动注册所有 Agent。移动目录后重新执行安装脚本。
MCP 自启动同一个 Windows 服务，关闭 GUI 不影响 Agent 调用；新会话发现工具即可使用。

## 上传与构建

将本文件所在 `EEDP-Nexus/` 作为 Git 仓库根目录。`.gitignore` 已排除环境、日志、凭据和生成包。
Release ZIP 单独上传 Releases；不要把自己的 `.state`、固件或个人配置发给别人。

```powershell
py -3.12 -m venv .packaging-venv
.\.packaging-venv\Scripts\python.exe -m pip install -r build-requirements.txt
.\.packaging-venv\Scripts\python.exe build_app.py
```

产物为 `dist/EEDP Nexus/` 和 `release/EEDP-Nexus-v0.5.0-win64.zip`。

Codex 接入方式依据 [官方 MCP 文档](https://developers.openai.com/codex/mcp) 与
[官方 Skills 文档](https://developers.openai.com/codex/skills)。
