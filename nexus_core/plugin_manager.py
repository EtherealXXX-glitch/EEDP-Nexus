"""Trusted local plugins with a versioned manifest and explicit lifecycle."""
import importlib.util
import json
from pathlib import Path
import re
import sys


class Plugins:
    def __init__(self, directory, registry):
        self.directory = Path(directory).resolve()
        self.registry = registry
        self.entries = {}
        registry.plugin_manager = self

    def _load(self, folder):
        manifest = json.loads((folder / "plugin.json").read_text(encoding="utf-8"))
        if manifest.get("api_version") != 1: raise ValueError("Unsupported plugin API version")
        identifier = manifest.get("id", "")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", identifier): raise ValueError("Invalid plugin id")
        if not all(manifest.get(k) for k in ("name", "version", "entrypoint")): raise ValueError("Incomplete manifest")
        if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?",manifest["version"]): raise ValueError("Plugin version must be semantic")
        if manifest.get("schema_version","1.0") not in ("1.0","1.1"): raise ValueError("Unsupported component schema")
        ui = manifest.get("ui", {"view":"generic"})
        if not isinstance(ui,dict) or ui.get("view","generic") not in ("generic","serial","beken","logic"):
            raise ValueError("Unsupported component view; use generic for new components")
        if ui.get("view") in ("serial","beken","logic") and identifier != {"serial":"serial","beken":"beken","logic":"slogic"}[ui["view"]]:
            raise ValueError("Built-in view does not match component id")
        manifest["ui"] = ui
        if manifest.get("schema_version") == "1.1":
            document=(folder/manifest.get("documentation","README.md")).resolve()
            if not document.is_relative_to(folder.resolve()) or not document.is_file(): raise ValueError("Component README is required")
        filename, class_name = manifest["entrypoint"].split(":", 1)
        entry = (folder / filename).resolve()
        if not entry.is_relative_to(folder.resolve()) or not entry.is_file(): raise ValueError("Plugin entry must be inside its folder")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", class_name): raise ValueError("Invalid component class")
        manifest.update(path=str(folder), entry=str(entry), class_name=class_name)
        return manifest

    def rescan(self):
        with self.registry.lock:
            found = {}
            for folder in sorted(self.directory.iterdir()):
                if not folder.is_dir() or not (folder / "plugin.json").exists(): continue
                try:
                    manifest = self._load(folder)
                    identifier = manifest["id"]
                    if identifier in found: raise ValueError("Duplicate plugin id")
                    found[identifier] = manifest
                except Exception as exc:
                    self.registry.activity.emit("workbench", "error", f"插件 {folder.name}: {exc}")
            for identifier in set(self.entries) - set(found):
                if identifier in self.registry.components: self._disable(identifier)
            self.entries = found
            saved = self.registry.settings.get("plugins") if self.registry.settings else {}
            for identifier in found:
                if saved.get(identifier, True) and identifier not in self.registry.components:
                    try: self._enable(identifier)
                    except Exception as exc: self.entries[identifier]["error"] = str(exc)
            return self.list()

    def _enable(self, identifier):
        manifest = self.entries[identifier]
        name = "workbench_plugin_" + identifier
        spec = importlib.util.spec_from_file_location(name, manifest["entry"])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        component = getattr(module, manifest["class_name"])(self.registry.activity, self.registry.resources)
        if component.id != identifier or not isinstance(component.actions, dict):
            component.close()
            raise ValueError("Component does not match its manifest")
        for action in component.actions:
            if not re.fullmatch(r"[a-z][a-z0-9_]*", action) or not callable(getattr(component, action, None)):
                component.close()
                raise ValueError("Invalid action contract")
            definition=component.actions[action]
            if manifest.get("schema_version") == "1.1":
                if not isinstance(definition.get("read_only"),bool) or not isinstance(definition.get("destructive"),bool):
                    component.close()
                    raise ValueError("Each v1.1 operation must declare read_only and destructive")
                if definition["read_only"] and definition["destructive"]:
                    component.close()
                    raise ValueError("Read-only action cannot be destructive")
        component.ui = manifest["ui"]
        component.plugin_version = manifest["version"]
        self.registry.register(component)
        manifest.pop("error", None)

    def _disable(self, identifier):
        component = self.registry.components.get(identifier)
        if not component: return
        if self.registry.in_flight.get(identifier,0): raise ValueError("组件调用仍在执行，请稍候再禁用")
        status = component.status()
        if identifier in self.registry.resources.status().values() or status.get("state") == "running" or status.get("connected"):
            raise ValueError("插件正在使用设备；请先显式断开或完成任务")
        component.close()
        del self.registry.components[identifier]

    def set_enabled(self, identifier, enabled):
        if not isinstance(enabled, bool): raise ValueError("enabled must be boolean")
        with self.registry.lock:
            if identifier not in self.entries: raise ValueError("Unknown plugin")
            if enabled and identifier not in self.registry.components: self._enable(identifier)
            if not enabled: self._disable(identifier)
            if self.registry.settings: self.registry.settings.update("plugins", {identifier: enabled})
            return self.list()

    def list(self):
        with self.registry.lock:
            return [dict(id=k, name=v["name"], version=v["version"], api_version=v["api_version"],
                         enabled=k in self.registry.components, path=v["path"], error=v.get("error", ""),
                         schema_version=v.get("schema_version","1.0"), ui=v.get("ui",{"view":"generic"}))
                    for k, v in self.entries.items()]
