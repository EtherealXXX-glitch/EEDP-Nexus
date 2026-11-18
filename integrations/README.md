# Agent 配置

请优先在 Windows 运行 `install-agent.cmd`（WSL 加 `-Wsl`），自动注册当前用户。
本目录的 TOML/JSON 只是结构示例，其中 `/path/to` 或 `C:/path/to` 必须替换。
可直接导入的本机配置由安装器生成在 `.state/agent-config/mcp.json`，不会上传 Git。
安装器支持 Codex；其他 Agent 根据其 stdio MCP 配置入口导入 JSON，并加载 Skill。
