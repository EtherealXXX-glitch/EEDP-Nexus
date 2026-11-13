"""Location-independent per-user MCP/Skill registration; no hardware operations."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
try:
    import tomllib
except ModuleNotFoundError:
    from vendor import tomli as tomllib


def write(path,text):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8-sig")==text:return
    if path.exists():shutil.copy2(path,path.with_name(path.name+f".pre-nexus-{time.time_ns()}"))
    temporary=path.with_name(path.name+".nexus-tmp")
    temporary.write_text(text,encoding="utf-8")
    os.replace(temporary,path)


def configure(root,home,*,wsl=False,codex_home=None,plan=False):
    root,home=Path(root).resolve(),Path(home)
    packaged=(root/"EEDP-Agent.exe").is_file()
    if not packaged and not (root/"run-workbench.py").is_file():
        raise ValueError("Select the EEDP Nexus source or unpacked application directory")
    if wsl:
        command="python3"
        args=[str(root/("agent_bridge/mcp-bridge.py" if packaged else "mcp-bridge.py"))]
    elif packaged:
        command=str(root/"EEDP-Agent.exe")
        args=["mcp"]
    else:
        python=root/".venv/Scripts/python.exe"
        if not python.is_file():raise ValueError("Run install-agent.ps1 to create the Windows Python environment first")
        command=str(python)
        args=[str(root/"run-workbench.py"),"mcp"]
    skill=root/"skills/use-agent-workbench"
    if not (skill/"SKILL.md").is_file():raise ValueError("Bundled Skill is missing")
    # Validate existing TOML before changing any settings; preserve other servers.
    config=(Path(codex_home) if codex_home else home/".codex")/"config.toml"
    old=config.read_text(encoding="utf-8-sig") if config.exists() else ""
    tomllib.loads(old)
    sections=re.split(r"(?m)(?=^\s*\[(?!\[))",old)
    kept=[]
    for section in sections:
        header=re.match(r"\s*\[([^\]\n]+)\]",section)
        if header and re.match(r'^mcp_servers\.(?:agent-workbench|"agent-workbench"|\'agent-workbench\')(?:\.|$)',header[1].strip()):continue
        kept.append(section)
    block="\n[mcp_servers.agent-workbench]\ncommand = "+json.dumps(command,ensure_ascii=False)+"\nargs = "+json.dumps(args,ensure_ascii=False)+"\n"
    updated="".join(kept).rstrip()+"\n"+block
    tomllib.loads(updated)
    destination=home/".agents/skills/use-agent-workbench"
    exported=root/".state/agent-config"/("mcp-wsl.json" if wsl else "mcp.json")
    if plan:
        return dict(root=str(root),config=str(config),config_text=updated,skill_source=str(skill),skill=str(destination),
            pointer=str(home/".eedp-agent.json"),pointer_text=json.dumps(dict(root=str(root)),ensure_ascii=False,indent=2)+"\n",
            generic_mcp=str(exported),generic_text=json.dumps(dict(mcpServers={"agent-workbench":dict(command=command,args=args)}),ensure_ascii=False,indent=2)+"\n")
    if destination.is_symlink():
        # Keep existing symlink installs, but replace the link rather than writing through it.
        destination.unlink()
    if destination.resolve()!=skill.resolve():
        shutil.copytree(skill,destination,dirs_exist_ok=True,ignore=shutil.ignore_patterns("__pycache__","*.pyc"))
    write(config,updated)
    write(home/".eedp-agent.json",json.dumps(dict(root=str(root)),ensure_ascii=False,indent=2)+"\n")
    write(exported,json.dumps(dict(mcpServers={"agent-workbench":dict(command=command,args=args)}),ensure_ascii=False,indent=2)+"\n")
    return dict(root=str(root),config=str(config),skill=str(destination),generic_mcp=str(exported),hardware_touched=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description="Register EEDP Nexus MCP and Skill for the current user")
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parent)
    parser.add_argument("--home",type=Path,default=Path.home())
    parser.add_argument("--wsl",action="store_true",help="Also register the default WSL distribution (run from Windows)")
    parser.add_argument("--plan",action="store_true",help="Print a registration plan without changing files")
    args=parser.parse_args(argv)
    result=configure(args.root,args.home,wsl=os.name!="nt",codex_home=os.environ.get("CODEX_HOME"),plan=args.plan)
    print(json.dumps(result,ensure_ascii=args.plan))
    if args.plan:return
    if args.wsl and os.name=="nt":
        script=args.root/"setup-agent.py"
        linux=subprocess.check_output(["wsl.exe","-e","wslpath","-u",str(script.resolve())],text=True).strip()
        subprocess.run(["wsl.exe","-e","python3",linux],check=True)
    print("Agent setup complete. Start a new Agent session to load MCP and Skill. No device was connected or written.")


if __name__=="__main__":main()
