# Workbench Plugin API v1

权威规范及迁移要求见 [COMPONENT-STANDARD.md](COMPONENT-STANDARD.md)，当前 schema 为 1.1，API 主版本仍为 1。
本文为入门摘要。新组件须声明 schema_version、README、ui.view 及每个动作的 read_only/destructive；默认使用 generic 视图。

每个插件是 `plugins/<目录>/` 下的独立包，包含自己的实现与 `plugin.json`。
主程序扫描清单，不导入固定的串口或烧录模块。插件是当前用户信任的本地 Python 代码，不是隔离沙箱。

```json
{
  "api_version": 1,
  "id": "example",
  "name": "Example",
  "version": "1.0.0",
  "entrypoint": "component.py:Example"
}
```

入口必须在插件目录内。入口类契约：

```python
from core import field

class Example:
    id = "example"
    name = "Example"
    description = "Query an example capability"
    actions = {"query": {"label": "查询", "fields": [field("name", "名称", "") ]}}

    def __init__(self, activity, resources):
        self.activity, self.resources = activity, resources

    def query(self, name=""):
        return {"name": name}

    def status(self):
        return {"state": "idle"}

    def close(self):
        pass
```

- `actions` 为 Agent 公开能力，只能声明可调用的公开方法。参数由 `field()` 声明类型、默认值与可选枚举。
- 写入或中止设备的动作应声明 `destructive: true`。界面和 MCP 根据动作元信息呈现。
- 动作结果必须可 JSON 序列化；异步操作应立即返回任务状态，使用 `status` 查询，不能长时间阻塞调用锁。
- 获取设备前调用 `resources.acquire(resource, self.id)`；结束或异常时必须释放。
- `status()` 应反映 `connected` 或 `state: running`，供插件管理器阻止卸载活动组件。
- `close()` 负责停止后台工作与释放资源。通信数据通过 `activity.emit()` 写入共享日志。
- 插件不依赖桌面界面，不直接调用其他插件。跨插件流程由 Agent 显式编排。

安装：将完整包放入 `plugins/`，执行 `plugins.rescan`。禁用：执行 `plugins.set`，`enabled=false`。
拆卸：先禁用，再把该插件目录移出 `plugins/`，然后扫描；不修改核心代码。
更新：先停用，替换包，再启用。启停设置保留在 `.state/settings.json`。
活动插件不会被静默断开；无效插件会记录错误，不阻止其他插件加载。

插件动作同时映射为 CLI `example.query` 和 MCP `example__query`。插件禁用后两种入口均不可调用。
