#!/usr/bin/env python3
"""Provision the verified bundled numerical toolchain into the container image."""

from __future__ import annotations

import os
from pathlib import Path

from toolkit_runtime.runtime import prepare_toolchain


runtime_root = Path(os.environ.get("KERR_QNM_TOOLKIT_RUNTIME", "/opt/kerr-qnm-runtime"))
result = prepare_toolchain(
    runtime_root=str(runtime_root),
    install_julia=True,
    install_python=True,
    seed_julia_depot=True,
)
if not result.get("ok"):
    raise SystemExit(f"Toolchain provisioning failed: {result}")
print(f"Prepared verified Kerr QNM runtime at {runtime_root}")
