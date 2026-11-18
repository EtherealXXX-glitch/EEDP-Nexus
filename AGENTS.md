# EEDP Nexus

Before first use, read the root [SKILL.md](SKILL.md). When the user asks to use or
initialize this workbench and registration is missing, perform its bootstrap workflow
automatically; verify existing registration first to avoid reinstalling on every turn.

Read README.md and COMPONENT-STANDARD.md before changing components. Keep manifests,
component documentation, this standard, Skills and relevant tests synchronized.

For first use after cloning on a Windows computer, run `install-agent.cmd`; add `-Wsl`
to register the default WSL user too. Windows Python 3.12+ with tkinter is required
for source checkouts. Reopen the Agent session after registration. Never register
someone else's absolute installation paths. MCP name `agent-workbench` and Skill
name `use-agent-workbench` are stable compatibility identifiers.

Use MCP discovery or the bundled Skill to query status before taking hardware ownership.
Installation, automated tests and packaging must never transmit, capture or flash physical devices.
Run `python check-components.py` and relevant unit tests before packaging.

Build: install build-requirements.txt into a Python 3.12+ environment and run build_app.py.
Generated artifacts and `.state` are ignored by Git; never commit live tokens, logs or firmware.
