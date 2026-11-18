# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

root = Path(SPECPATH)
icon = str(root / "assets/nexus-hub.ico")
analysis = Analysis([str(root / "run-workbench.py")], pathex=[str(root)], binaries=[],
    datas=[(str(root / "assets"), "assets")],
    hiddenimports=["serial", "serial.serialwin32", "serial.win32", "serial.tools.list_ports", "serial.tools.list_ports_windows", "serial.urlhandler.protocol_loop", "configparser"],
    hookspath=[], runtime_hooks=[], excludes=["PIL", "unittest", "pytest"], noarchive=False)
pyz = PYZ(analysis.pure)

def version(original, description):
    return VSVersionInfo(ffi=FixedFileInfo(filevers=(0,5,0,0), prodvers=(0,5,0,0), mask=0x3f,
        flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0,0)), kids=[
        StringFileInfo([StringTable('080404b0', [StringStruct('CompanyName','EEDP'),
            StringStruct('FileDescription',description), StringStruct('FileVersion','0.5.0'),
            StringStruct('ProductName','EEDP Nexus'), StringStruct('ProductVersion','0.5.0'),
            StringStruct('OriginalFilename',original), StringStruct('InternalName','EEDP-Agent')])]),
        VarFileInfo([VarStruct('Translation',[2052,1200])])])

gui = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='EEDP Nexus',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False,
    icon=icon, version=version('EEDP Nexus.exe','EEDP Nexus'))
cli = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='EEDP-Agent',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=True,
    icon=icon, version=version('EEDP-Agent.exe','EEDP-Agent 工作台 Agent 接口'))
bundle = COLLECT(gui, cli, analysis.binaries, analysis.datas, strip=False, upx=False, name='EEDP Nexus')
