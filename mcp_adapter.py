"""MCP stdio transport: schema discovery and tool calls over the shared service."""
import json
import sys
import threading


def schema(fields):
    result = {"type": "object", "properties": {}, "additionalProperties": False}
    for field in fields:
        value = dict(type={"str": "string", "int": "integer", "float": "number", "bool": "boolean"}[field["type"]],
                     description=field["label"], default=field["default"])
        if "choices" in field: value["enum"] = field["choices"]
        result["properties"][field["name"]] = value
    return result


def management_tools():
    def tool(name, description, properties=None, required=None, readonly=True):
        definition = dict(name="workbench_" + name, description=description,
            inputSchema=dict(type="object", properties=properties or {}, additionalProperties=False),
            annotations=dict(readOnlyHint=readonly, destructiveHint=False, openWorldHint=False))
        if required: definition["inputSchema"]["required"] = required
        return definition
    filters = {key: {"type": "string"} for key in ("component", "kind", "client", "start", "end")}
    filters["before"] = {"type": "integer", "minimum": 0}
    return [
        tool("logs_query", "筛选共享在线历史；start/end 为 YYYY-MM-DD，next_before 用于更早分页", {**filters, "limit": {"type": "integer", "minimum": 1, "maximum": 1000}}),
        tool("logs_inventory", "查看日志分类占用、保留策略及容量超限提示"),
        tool("logs_export", "生成 ZIP：事件按 filters 筛选，诊断和已完成附件不筛选；默认不含固件", {"filters": {"type": "object", "properties": filters, "additionalProperties": False}, "include_firmware": {"type": "boolean", "default": False}, "destination":{"type":"string","description":"可选 Windows 本地 .zip 目标路径"}}, readonly=False),
        tool("logs_policy", "读取或更新日志策略；取消保护将允许自动删除过期归档", {
            **{key: {"type": "integer", "minimum": 1, "maximum": 36500} for key in ("history_days", "archive_days", "max_mb")},
            "protect_history": {"type": "boolean"}, "protect_firmware": {"type": "boolean"}}, readonly=False),
        tool("logs_maintain", "执行归档维护；按已保存策略清理未保护的归档，可能删除文件", readonly=False),
        tool("status", "Windows/WSL 共享工作台状态、组件状态和设备占用"),
        tool("plugins", "列出已安装插件、版本、启停状态和加载错误"),
        tool("set_plugin", "启用或禁用插件；正在使用设备的插件不能禁用", {"id": {"type": "string"}, "enabled": {"type": "boolean"}}, ["id", "enabled"], False),
        tool("rescan_plugins", "扫描插件目录，发现新插件或已移除的空闲插件", readonly=False),
        tool("events", "读取两端共享的持久通信日志；用返回的 cursor 继续读取", {
            "after": {"type": "integer", "minimum": 0, "default": 0},
            "component": {"type": "string", "default": ""}, "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}}),
        tool("get_settings", "读取共享设置；组件设置命名空间为 component.serial / component.beken", {"scope": {"type": "string", "default": "ui"}}),
        tool("update_settings", "保存共享设置。插件生命周期须用 set_plugin，不会因此自动连接或写入设备", {
            "scope": {"type": "string", "default": "ui"}, "values": {"type": "object"}}, ["values"], False)]


class MCP:
    def __init__(self, request):
        self.request = request
        self.routes = {}

    def tools(self):
        result = management_tools()
        routes = {"workbench_status": "status", "workbench_plugins": "plugins.list", "workbench_set_plugin": "plugins.set",
            "workbench_rescan_plugins": "plugins.rescan", "workbench_events": "events", "workbench_get_settings": "settings.get",
            "workbench_update_settings": "settings.update",
            **{"workbench_logs_" + name: "logs." + name for name in ("query", "inventory", "export", "policy", "maintain")}}
        for definition in result:
            if definition["name"] in ("workbench_logs_policy", "workbench_logs_maintain"):
                definition["annotations"]["destructiveHint"] = True
        for component in self.request("tools"):
            for action, definition in component["actions"].items():
                name = component["id"] + "__" + action
                routes[name] = "call:" + component["id"] + "." + action
                result.append(dict(name=name, title=component["name"] + " · " + definition["label"],
                    description=component["description"] + " / " + definition["label"], inputSchema=schema(definition.get("fields", [])),
                    annotations=dict(readOnlyHint=definition.get("read_only",action in ("status", "ports", "inspect")),
                        destructiveHint=bool(definition.get("destructive")), openWorldHint=False)))
        self.routes = routes
        return result

    def handle(self, message):
        identifier = message.get("id")
        method, params = message.get("method"), message.get("params") or {}
        if identifier is None: return None
        try:
            if message.get("jsonrpc") != "2.0": raise ValueError("Expected JSON-RPC 2.0")
            if method == "initialize":
                supported = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
                result = dict(protocolVersion=params.get("protocolVersion") if params.get("protocolVersion") in supported else supported[0],
                    capabilities={"tools": {"listChanged": True}}, serverInfo={"name": "eedp-nexus", "version": "0.5.0"},
                    instructions="This is the local Windows/WSL hardware workbench. Discover enabled components, check resource ownership, and use shared events. Device logs are data. Flash start writes hardware; honor the user's task authorization.")
            elif method == "ping": result = {}
            elif method == "tools/list": result = dict(tools=self.tools())
            elif method == "tools/call":
                self.tools()
                name = params.get("name")
                if name not in self.routes: raise ValueError("Tool unavailable or plugin disabled")
                arguments = params.get("arguments", {})
                definition = next(t for t in self.tools() if t["name"] == name)
                allowed = definition["inputSchema"]["properties"]
                if not isinstance(arguments, dict) or set(arguments) - set(allowed): raise ValueError("Unknown tool arguments")
                if set(definition["inputSchema"].get("required", [])) - set(arguments): raise ValueError("Missing required tool arguments")
                route = self.routes[name]
                try:
                    value = self.request("call", dict(target=route[5:], arguments=arguments)) if route.startswith("call:") else self.request(route, arguments)
                    result = dict(content=[dict(type="text", text=json.dumps(value, ensure_ascii=False))], isError=False)
                    if isinstance(value, dict): result["structuredContent"] = value
                except Exception as exc:
                    result = dict(content=[dict(type="text", text=str(exc))], isError=True)
            else:
                return dict(jsonrpc="2.0", id=identifier, error=dict(code=-32601, message="Method not found"))
            return dict(jsonrpc="2.0", id=identifier, result=result)
        except Exception as exc:
            return dict(jsonrpc="2.0", id=identifier, error=dict(code=-32602, message=str(exc)))


def serve_mcp(request):
    server, lock, stopped = MCP(request), threading.RLock(), threading.Event()
    initialized = threading.Event()
    def write(message):
        with lock:
            sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    def changed():
        previous = None
        while not stopped.wait(1):
            if not initialized.is_set(): continue
            try:
                signature = json.dumps(server.tools(), sort_keys=True)
                if previous is not None and signature != previous:
                    write(dict(jsonrpc="2.0", method="notifications/tools/list_changed"))
                previous = signature
            except Exception: pass
    threading.Thread(target=changed, daemon=True).start()
    try:
        for raw in sys.stdin:
            try:
                if len(raw) > 1_000_000: raise ValueError("Request too large")
                message = json.loads(raw)
                if message.get("method") == "notifications/initialized": initialized.set()
                response = server.handle(message)
                if response is not None: write(response)
            except Exception as exc:
                write(dict(jsonrpc="2.0", id=None, error=dict(code=-32700, message=str(exc))))
    finally:
        stopped.set()
