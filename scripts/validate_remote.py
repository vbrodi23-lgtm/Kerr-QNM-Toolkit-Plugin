#!/usr/bin/env python3
"""Validate the registered remote MCP tool surface without starting a socket."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))


with tempfile.TemporaryDirectory(prefix="kerr-qnm-workspace-") as temporary:
    os.environ["KERR_QNM_WORKSPACE_ROOT"] = str(Path(temporary).resolve())
    os.environ.setdefault("KERR_QNM_ALLOWED_HOSTS", "localhost,localhost:*")
    import remote_server

    tools = asyncio.run(remote_server.mcp.list_tools())

expected = {
    "kerr_qnm_toolchain_status",
    "kerr_qnm_inspect_workspace",
    "kerr_qnm_git_inspect",
    "kerr_qnm_list_files",
    "kerr_qnm_read_text_file",
    "kerr_qnm_search_text",
    "kerr_qnm_git_diff",
    "kerr_qnm_apply_patch",
    "kerr_qnm_run_julia_file",
    "kerr_qnm_run_python_file",
    "kerr_qnm_julia_project",
    "kerr_qnm_python_tests",
    "kerr_qnm_jsonl_probe",
    "kerr_qnm_numerical_canary",
}
names = {tool.name for tool in tools}
if names != expected:
    raise SystemExit(f"Unexpected tool surface: missing={sorted(expected - names)}, extra={sorted(names - expected)}")
if any(tool.annotations is None for tool in tools):
    raise SystemExit("Every remote tool must declare behavioral annotations.")
patch_tool = next(tool for tool in tools if tool.name == "kerr_qnm_apply_patch")
if not patch_tool.annotations.destructive_hint or patch_tool.annotations.read_only_hint:
    raise SystemExit("Patch tool annotations do not describe its write behavior.")
print(f"Remote MCP validation passed: {len(tools)} annotated tools")
