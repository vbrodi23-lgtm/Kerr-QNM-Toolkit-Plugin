#!/usr/bin/env python3
"""Initialize the persistent solver workspace and start the remote MCP server."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


plugin_root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(plugin_root / "scripts" / "bootstrap_workspace.py")], check=True)
os.execv(sys.executable, [sys.executable, str(plugin_root / "remote_server.py")])
