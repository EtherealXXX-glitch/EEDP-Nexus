"""Reproducible portable distribution; does not include live state or credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent


def main():
    target = (ROOT / "dist/EEDP Nexus").resolve()
    if not target.is_relative_to(ROOT.resolve()) or (target / ".state").exists():
        raise RuntimeError("Refusing to overwrite a live application or a path outside this workspace")
    subprocess.run([sys.executable, str(ROOT / "build_assets.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "build_sidebar_icons.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "build_button_assets.py")], check=True)
    subprocess.run([sys.executable, str(ROOT / "check-components.py")], check=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", str(ROOT / "eedp-agent.spec")], cwd=ROOT, check=True,
                   env={**os.environ, "PYTHONUTF8":"1"})
    distribution = ROOT / "dist/EEDP Nexus"
    shutil.copytree(ROOT / "plugins", distribution / "plugins", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(ROOT / "component-plans", distribution / "component-plans", dirs_exist_ok=True)
    engine = Path(os.environ.get("EEDP_BEKEN_ENGINE",str(ROOT / "plugins/beken/bin/bk_loader.exe")))
    if not engine.is_file(): raise FileNotFoundError("Place the vendor bk_loader.exe in plugins/beken/bin or set EEDP_BEKEN_ENGINE")
    destination = distribution / "plugins/beken/bin/bk_loader.exe"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(engine, destination)
    bridge = distribution / "agent_bridge"
    bridge.mkdir(exist_ok=True)
    for name in ("bridge_client.py", "mcp_adapter.py", "mcp-bridge.py"):
        shutil.copy2(ROOT / name, bridge / name)
    for name in ("agent_setup.py","setup-agent.py","install-agent.ps1","install-agent.cmd"):
        shutil.copy2(ROOT/name,distribution/name)
    shutil.copytree(ROOT/"vendor",distribution/"vendor",dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    shutil.copytree(ROOT / "skills", distribution / "skills", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(ROOT / "PLUGIN-API.md", distribution / "插件开发说明.md")
    shutil.copy2(ROOT / "COMPONENT-STANDARD.md", distribution / "组件开发标准手册.md")
    shutil.copy2(ROOT / "GETTING-STARTED.md", distribution / "GETTING-STARTED.md")
    shutil.copy2(ROOT / "SKILL.md", distribution / "SKILL.md")
    shutil.copy2(ROOT / "AGENTS.md", distribution / "AGENTS.md")
    (distribution / "使用说明.txt").write_text(
        "EEDP Nexus 0.5.0 — Windows 免安装版\n\n"
        "双击 EEDP Nexus.exe 打开界面，不需要安装 Python。\n"
        "运行 install-agent.cmd 注册 Windows Agent；install-agent.cmd -Wsl 同时注册默认 WSL 用户，然后新开 Agent 会话。\n"
        "请保留整个文件夹，_internal 是内置运行环境，plugins 是可拆卸组件。\n"
        "EEDP-Agent.exe 为 Agent 命令接口，支持 tools、status、call、rpc、mcp 等命令。\n"
        "界面“Agent 接口”提供当前位置的 Windows / WSL MCP 配置。\n"
        "WSL MCP 使用 python3 agent_bridge/mcp-bridge.py，仅依赖 Linux Python 标准库。\n"
        "使用技能位于 skills/use-agent-workbench，按需安装到 Agent 的技能目录。\n"
        "运行设置和日志保存在本软件目录下的 .state，升级前保留该目录。\n"
        "右侧日志中心或文件菜单可按日期、插件、事件、来源查询历史并导出 ZIP；存储与归档页可调整保留策略。\n"
        "设置 → 外观提供六套配色、按钮字体/字号/字重、图标显示及侧栏图标大小，选择会记忆。\n"
        "底部 Agent 桥接状态可点击查看后台和设备占用，顶部文件/视图/设备/工具/帮助菜单均为实际功能。\n"
        "默认在线保留 30 天、约 10 万条，归档 90 天，容量目标 512 MB；历史和固件默认保护，超限提示。\n"
        "本版本含串口监控与 Beken 烧录插件；bk_loader 为本机原厂引擎。\n"
        "关闭窗口后后台监控继续，菜单可停止后台服务。\n", encoding="utf-8-sig")
    archive = ROOT / "release/EEDP-Nexus-v0.5.0-win64.zip"
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip:
        for path in distribution.rglob("*"):
            if path.is_file() and ".state" not in path.relative_to(distribution).parts:
                zip.write(path, str(Path(distribution.name) / path.relative_to(distribution)))
    print(json.dumps(dict(directory=str(distribution), zip=str(archive), bytes=archive.stat().st_size), ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
