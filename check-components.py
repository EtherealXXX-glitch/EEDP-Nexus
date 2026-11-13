"""Validate plugin manifests and runtime schemas without opening hardware."""
import importlib.util
import json
from pathlib import Path
import tempfile

from core import Activity, Registry, Resources
from plugin_manager import Plugins
from settings import Settings


def main():
    root=Path(__file__).resolve().parent
    temporary=root/"build/test-artifacts"
    temporary.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=temporary) as directory:
        state=Path(directory)
        registry=Registry(Activity(state/"logs"),Resources(),Settings(state/"settings.json"))
        try:
            manager=Plugins(root/"plugins",registry)
            entries=manager.rescan()
            folders=list((root/"plugins").glob("*/plugin.json"))
            assert len(entries)==len(folders),"A component manifest failed validation"
            for plugin in entries:
                assert plugin["enabled"] and not plugin["error"],plugin
                assert plugin["schema_version"]=="1.1",plugin
            for component in registry.describe():
                assert "status" in component["actions"]
                for name,action in component["actions"].items():
                    assert isinstance(action.get("read_only"),bool),(component["id"],name)
                    assert isinstance(action.get("destructive"),bool),(component["id"],name)
                    assert action.get("label")
                    fields=action.get("fields",[])
                    assert len({f["name"] for f in fields})==len(fields)
                    for field in fields:
                        assert field["type"] in ("str","int","float","bool")
                        assert "default" in field and field["label"]
            assert registry.resources.status()=={},"Validation acquired a hardware resource"
            print(json.dumps(dict(schema_version="1.1",components=[x["id"] for x in entries],
                actions=sum(len(c["actions"]) for c in registry.describe()),hardware_access=False)))
        finally: registry.close()


if __name__=="__main__":main()
