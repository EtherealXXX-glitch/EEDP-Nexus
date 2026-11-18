"""Versioned operations shared by the UI, CLI, WSL bridge and MCP adapter."""
VERSION = "0.5.0"


def dispatch(registry, method, params=None, client="unknown"):
    params = params or {}
    if method == "tools": return registry.describe()
    if method == "status":
        with registry.lock:
            return dict(api_version=1, version=VERSION, resources=registry.resources.status(),
                        components={k: v.status() for k, v in registry.components.items()},
                        logs=str(registry.activity.directory), session=registry.activity.session,
                        event_cursor=registry.activity.sequence)
    if method == "events": return registry.activity.read(**params)
    if method == "logs.query": return registry.logs.query(**params)
    if method == "logs.inventory": return registry.logs.inventory()
    if method == "logs.export": return registry.logs.export(**params)
    if method == "logs.policy":
        if not params: return registry.logs.policy()
        result = registry.logs.set_policy(**params)
        registry.activity.emit("workbench", "policy", "更新日志保留策略", client=client)
        return result
    if method == "logs.maintain":
        result = registry.logs.maintain()
        registry.activity.emit("workbench", "maintenance", "归档维护：" + str({k:v for k,v in result.items() if k != "inventory"}), client=client)
        return result
    if method == "call": return registry.invoke(params["target"], params.get("arguments", {}), client=client)
    if method == "settings.get": return registry.settings.get(params.get("scope", "ui"))
    if method == "settings.update":
        scope = params.get("scope", "ui")
        if scope in ("plugins", "logs"): raise ValueError("Use plugins.set or logs.policy for managed settings")
        result = registry.settings.update(scope, params["values"])
        registry.activity.emit("workbench", "settings", f"更新设置 {scope}", client=client)
        return result
    manager = registry.plugin_manager
    if method == "plugins.list": return manager.list()
    if method == "plugins.rescan":
        result = manager.rescan()
        registry.activity.emit("workbench", "plugins", "重新扫描插件", client=client)
        return result
    if method == "plugins.set":
        result = manager.set_enabled(params["id"], params["enabled"])
        registry.activity.emit("workbench", "plugins", f"{params['id']} enabled={params['enabled']}", client=client)
        return result
    raise ValueError("Unknown workbench method: " + method)
