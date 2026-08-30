#!/usr/bin/env python3
"""Clone a configured solver repository only when the persistent workspace is empty."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


root = Path(os.environ.get("KERR_QNM_WORKSPACE_ROOT", "/workspace")).resolve()
root.mkdir(parents=True, exist_ok=True)
repository = os.environ.get("KERR_QNM_SOLVER_REPOSITORY", "").strip()
reference = os.environ.get("KERR_QNM_SOLVER_REF", "").strip()

if any(root.iterdir()) or not repository:
    raise SystemExit(0)

parsed = urlsplit(repository)
if parsed.scheme not in {"https", "ssh"}:
    raise SystemExit("KERR_QNM_SOLVER_REPOSITORY must use HTTPS or SSH.")
if parsed.username or parsed.password:
    raise SystemExit("Do not embed credentials in KERR_QNM_SOLVER_REPOSITORY; use the hosting platform's secret or Git credential support.")

command = ["git", "clone", "--single-branch"]
if reference:
    command.extend(["--branch", reference])
command.extend([repository, str(root)])
completed = subprocess.run(command, check=False)
if completed.returncode:
    raise SystemExit(completed.returncode)
