"""Display-only roadmap entries; never imports code or registers callable actions."""
import json
from app_paths import ROOT


def planned_components():
    result=[]
    for path in sorted((ROOT/"component-plans").glob("*.json")):
        try:
            value=json.loads(path.read_text(encoding="utf-8"))
            if value.get("status")!="planned" or not value.get("id") or not value.get("name"):continue
            result.append({**value,"planned":True,"enabled":False,"version":"规划中","error":"","path":str(path.parent)})
        except (OSError,ValueError):continue
    return result
