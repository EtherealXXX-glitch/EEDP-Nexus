---
name: eedp-nexus-bootstrap
description: Bootstrap a cloned or unpacked EEDP Nexus installation for a Windows or WSL Agent, discover its MCP hardware tools, and install the bundled usage Skill when local registration is missing.
---

# EEDP Nexus 首次接入

当用户要求使用本仓库的工作台、接入 Agent，或初始化克隆后的项目时，先检查接入，缺失时直接初始化。
所有路径相对于本 SKILL.md 所在目录，不能使用原开发者的绝对路径。

1. 先尝试已连接 `agent-workbench` MCP 的 `workbench_status`；若可用且安装指针指向当前目录或其当前 release，可跳过安装，读取 `skills/use-agent-workbench/SKILL.md` 使用组件。
2. 未接入时，Windows 在本目录运行 `install-agent.cmd`。若用户的 Agent 在 WSL，在 **Windows PowerShell** 运行 `install-agent.cmd -Wsl`。
3. 如果当前 Agent 本身在 WSL，使用 Windows interop 调用同一初始化脚本（在本目录执行）：

   ```bash
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$PWD/install-agent.ps1")" -Wsl
   ```

   不要在 Linux shell 直接执行 `.cmd`，不要安装第二个 Linux 硬件守护进程。
4. Windows 源码模式需要 Python 3.12+（含 tkinter），安装器创建环境并安装 requirements；免安装版不需要 Python。若缺少 Python，说明该依赖或使用 Release ZIP，不得宣称安装成功。默认 WSL 用户不是当前用户时，改为在当前发行版执行 `python3 setup-agent.py`，避免把 Skill 只安装给其他用户。
5. 安装器自动记录实际路径，注册当前用户的 Codex MCP、复制使用 Skill，并备份修改的配置；不改其他 MCP 或模型配置。成功后运行只读检查 `check-interfaces.py`（源码提供）或使用安装后的 Skill helper 查询 `status`。
6. 已启动的 Agent 可能需要新开会话才能加载 MCP/Skill。当前会话工具列表未刷新时，读取 `skills/use-agent-workbench/SKILL.md`，按其 helper 继续调用同一后台；不要仅因工具未热加载就重复安装。

其他 MCP 客户端使用安装器生成的 `.state/agent-config/mcp.json`（Windows）或 `mcp-wsl.json`（WSL），按该客户端配置入口导入；不要宣称已自动注册所有 Agent。

初始化只准备接口，不连接串口、不发送字节、不采样、不烧录。硬件操作继续遵循用户任务授权、设备资源占用与组件规范。Beken 原厂引擎及 USB 驱动是独立依赖，不能把“Agent 接入完成”当成“所有硬件已就绪”。

更多说明：[GETTING-STARTED.md](GETTING-STARTED.md)。实际硬件调用技能：[skills/use-agent-workbench/SKILL.md](skills/use-agent-workbench/SKILL.md)。
