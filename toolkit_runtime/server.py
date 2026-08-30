#!/usr/bin/env python3
"""Stdio MCP server for Kerr QNM Toolkit."""

from __future__ import annotations

import json
import sys
from typing import Any

from runtime import (
    ToolkitError,
    git_inspect,
    inspect_workspace,
    jsonl_probe,
    julia_project_action,
    numerical_canary,
    prepare_toolchain,
    python_tests,
    run_julia_file,
    run_python_file,
    toolchain_status,
)


SERVER_NAME = "kerr-qnm-toolkit"
SERVER_VERSION = "1.0.0"


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        result["required"] = required
    return result


def tool_definitions() -> list[dict[str, Any]]:
    absolute_path = {"type": "string", "description": "Absolute local filesystem path."}
    relative_path = {"type": "string", "description": "Path relative to workspace_root; parent traversal is rejected."}
    runtime_root = {
        **absolute_path,
        "description": "Optional managed runtime root; defaults to KERR_QNM_TOOLKIT_RUNTIME or the standard local path.",
    }
    timeout = {"type": "integer", "minimum": 1, "maximum": 1800, "default": 120}
    arguments = {"type": "array", "items": {"type": "string"}, "maxItems": 64, "default": []}
    julia_selection = {
        "type": "string",
        "enum": ["pinned", "compatible", "any"],
        "default": "compatible",
        "description": "Choose exact Julia 1.10.11, a 64-bit Julia 1.10+, or any available 64-bit Julia.",
    }
    python_selection = {
        "type": "string",
        "enum": ["managed", "compatible", "any"],
        "default": "compatible",
        "description": "Choose the exact managed numerical environment, a Python 3.10+, or any available 64-bit Python.",
    }
    return [
        {
            "name": "kerr_qnm_toolchain_status",
            "description": "Inspect the local Linux Julia/Python numerical toolchain and bundled asset inventory without changing it.",
            "inputSchema": _schema(
                {
                    "runtime_root": runtime_root,
                    "verify_assets": {
                        "type": "boolean",
                        "default": False,
                        "description": "Hash every bundled archive and wheel. This is read-only but can take several seconds.",
                    },
                }
            ),
        },
        {
            "name": "kerr_qnm_prepare_toolchain",
            "description": "Provision the bundled offline Julia, CPython, NumPy, SciPy, and optional Julia scientific depot in a local Linux runtime root.",
            "inputSchema": _schema(
                {
                    "runtime_root": runtime_root,
                    "install_julia": {"type": "boolean", "default": True},
                    "install_python": {"type": "boolean", "default": True},
                    "seed_julia_depot": {
                        "type": "boolean",
                        "default": True,
                        "description": "Extract the bundled Julia package cache for reproducible or offline project work.",
                    },
                }
            ),
        },
        {
            "name": "kerr_qnm_inspect_workspace",
            "description": "Discover Julia/Python projects, manifests, tests, likely entry points, notebooks, data files, GitHub workflows, and local Git state in any research workspace.",
            "inputSchema": _schema(
                {
                    "workspace_root": absolute_path,
                    "max_depth": {"type": "integer", "minimum": 1, "maximum": 12, "default": 6},
                    "max_files": {"type": "integer", "minimum": 100, "maximum": 20000, "default": 5000},
                },
                ["workspace_root"],
            ),
        },
        {
            "name": "kerr_qnm_git_inspect",
            "description": "Inspect repository root, branch, commit, dirty state, submodules, and credential-scrubbed remotes for a local workspace.",
            "inputSchema": _schema({"workspace_root": absolute_path}, ["workspace_root"]),
        },
        {
            "name": "kerr_qnm_run_julia_file",
            "description": "Run an existing Julia file beneath a selected workspace with optional project, depot, runtime, thread, offline, argument, and timeout controls.",
            "inputSchema": _schema(
                {
                    "workspace_root": absolute_path,
                    "script_relative": relative_path,
                    "arguments": arguments,
                    "project_relative": {**relative_path, "description": "Optional directory containing Project.toml."},
                    "depot_path": {**absolute_path, "description": "Optional existing Julia depot."},
                    "use_managed_depot": {"type": "boolean", "default": False},
                    "runtime_root": runtime_root,
                    "julia_selection": julia_selection,
                    "julia_executable": {**absolute_path, "description": "Optional explicit Julia executable."},
                    "threads": {"type": "integer", "minimum": 1, "maximum": 64, "default": 1},
                    "offline": {"type": "boolean", "default": False},
                    "timeout_seconds": timeout,
                },
                ["workspace_root", "script_relative"],
            ),
        },
        {
            "name": "kerr_qnm_run_python_file",
            "description": "Run an existing Python file beneath a selected workspace with managed, project-local, system, or explicit Python.",
            "inputSchema": _schema(
                {
                    "workspace_root": absolute_path,
                    "script_relative": relative_path,
                    "arguments": arguments,
                    "runtime_root": runtime_root,
                    "python_selection": python_selection,
                    "python_executable": {**absolute_path, "description": "Optional explicit Python executable."},
                    "interpreter_relative": {**relative_path, "description": "Optional workspace-relative Python executable such as .venv/bin/python."},
                    "isolated": {"type": "boolean", "default": False, "description": "Disable user site-packages."},
                    "timeout_seconds": timeout,
                },
                ["workspace_root", "script_relative"],
            ),
        },
        {
            "name": "kerr_qnm_julia_project",
            "description": "Run a structured Julia package action—status, instantiate, precompile, resolve, or test—against a selected Project.toml.",
            "inputSchema": _schema(
                {
                    "workspace_root": absolute_path,
                    "project_relative": {**relative_path, "default": "."},
                    "action": {"type": "string", "enum": ["status", "instantiate", "precompile", "resolve", "test"]},
                    "depot_path": {**absolute_path, "description": "Optional existing Julia depot."},
                    "use_managed_depot": {"type": "boolean", "default": False},
                    "runtime_root": runtime_root,
                    "julia_selection": julia_selection,
                    "julia_executable": {**absolute_path, "description": "Optional explicit Julia executable."},
                    "allow_network": {
                        "type": "boolean",
                        "default": False,
                        "description": "Permit Julia package operations to access configured package servers and registries.",
                    },
                    "threads": {"type": "integer", "minimum": 1, "maximum": 64, "default": 1},
                    "timeout_seconds": {**timeout, "default": 300},
                },
                ["workspace_root", "action"],
            ),
        },
        {
            "name": "kerr_qnm_python_tests",
            "description": "Run pytest or unittest on an existing target beneath a selected workspace with a managed, project-local, system, or explicit interpreter.",
            "inputSchema": _schema(
                {
                    "workspace_root": absolute_path,
                    "target_relative": {**relative_path, "default": "."},
                    "framework": {"type": "string", "enum": ["auto", "pytest", "unittest"], "default": "auto"},
                    "arguments": arguments,
                    "runtime_root": runtime_root,
                    "python_selection": python_selection,
                    "python_executable": {**absolute_path, "description": "Optional explicit Python executable."},
                    "interpreter_relative": {**relative_path, "description": "Optional workspace-relative Python executable."},
                    "timeout_seconds": {**timeout, "default": 300},
                },
                ["workspace_root"],
            ),
        },
        {
            "name": "kerr_qnm_jsonl_probe",
            "description": "Feed bounded JSON Lines input to an existing Julia or Python worker and validate that stdout is line-framed JSON.",
            "inputSchema": _schema(
                {
                    "workspace_root": absolute_path,
                    "language": {"type": "string", "enum": ["julia", "python"]},
                    "script_relative": relative_path,
                    "messages": {"type": "array", "items": {}, "minItems": 1, "maxItems": 32},
                    "arguments": arguments,
                    "project_relative": {**relative_path, "description": "Optional Julia project directory."},
                    "depot_path": {**absolute_path, "description": "Optional existing Julia depot."},
                    "use_managed_depot": {"type": "boolean", "default": False},
                    "runtime_root": runtime_root,
                    "julia_selection": julia_selection,
                    "julia_executable": {**absolute_path, "description": "Optional explicit Julia executable."},
                    "python_selection": python_selection,
                    "python_executable": {**absolute_path, "description": "Optional explicit Python executable."},
                    "interpreter_relative": {**relative_path, "description": "Optional workspace-relative Python executable."},
                    "strict_count": {"type": "boolean", "default": True},
                    "timeout_seconds": timeout,
                },
                ["workspace_root", "language", "script_relative", "messages"],
            ),
        },
        {
            "name": "kerr_qnm_numerical_canary",
            "description": "Run short deterministic checks for NumPy/SciPy numerics, Julia numerics, and their byte-exact cross-language file contract.",
            "inputSchema": _schema(
                {
                    "mode": {"type": "string", "enum": ["all", "python", "julia", "cross-language"], "default": "all"},
                    "runtime_root": runtime_root,
                    "julia_selection": {**julia_selection, "default": "pinned"},
                    "julia_executable": {**absolute_path, "description": "Optional explicit Julia executable."},
                    "python_selection": {**python_selection, "default": "managed"},
                    "python_executable": {**absolute_path, "description": "Optional explicit Python executable."},
                    "timeout_seconds": timeout,
                }
            ),
        },
    ]


def _arguments(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise ToolkitError("tools/call params must be an object.")
    arguments = params.get("arguments", {})
    if not isinstance(arguments, dict):
        raise ToolkitError("tools/call arguments must be an object.")
    return arguments


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "kerr_qnm_toolchain_status":
        return toolchain_status(arguments.get("runtime_root"), arguments.get("verify_assets", False))
    if name == "kerr_qnm_prepare_toolchain":
        return prepare_toolchain(
            arguments.get("runtime_root"),
            arguments.get("install_julia", True),
            arguments.get("install_python", True),
            arguments.get("seed_julia_depot", True),
        )
    if name == "kerr_qnm_inspect_workspace":
        return inspect_workspace(arguments["workspace_root"], arguments.get("max_depth", 6), arguments.get("max_files", 5000))
    if name == "kerr_qnm_git_inspect":
        return git_inspect(arguments["workspace_root"])
    if name == "kerr_qnm_run_julia_file":
        return run_julia_file(
            workspace_root=arguments["workspace_root"],
            script_relative=arguments["script_relative"],
            arguments=arguments.get("arguments"),
            project_relative=arguments.get("project_relative"),
            depot_path=arguments.get("depot_path"),
            use_managed_depot=arguments.get("use_managed_depot", False),
            runtime_root=arguments.get("runtime_root"),
            julia_selection=arguments.get("julia_selection", "compatible"),
            julia_executable=arguments.get("julia_executable"),
            threads=arguments.get("threads", 1),
            offline=arguments.get("offline", False),
            timeout_seconds=arguments.get("timeout_seconds", 120),
        )
    if name == "kerr_qnm_run_python_file":
        return run_python_file(
            workspace_root=arguments["workspace_root"],
            script_relative=arguments["script_relative"],
            arguments=arguments.get("arguments"),
            runtime_root=arguments.get("runtime_root"),
            python_selection=arguments.get("python_selection", "compatible"),
            python_executable=arguments.get("python_executable"),
            interpreter_relative=arguments.get("interpreter_relative"),
            isolated=arguments.get("isolated", False),
            timeout_seconds=arguments.get("timeout_seconds", 120),
        )
    if name == "kerr_qnm_julia_project":
        return julia_project_action(
            workspace_root=arguments["workspace_root"],
            project_relative=arguments.get("project_relative", "."),
            action=arguments["action"],
            depot_path=arguments.get("depot_path"),
            use_managed_depot=arguments.get("use_managed_depot", False),
            runtime_root=arguments.get("runtime_root"),
            julia_selection=arguments.get("julia_selection", "compatible"),
            julia_executable=arguments.get("julia_executable"),
            allow_network=arguments.get("allow_network", False),
            threads=arguments.get("threads", 1),
            timeout_seconds=arguments.get("timeout_seconds", 300),
        )
    if name == "kerr_qnm_python_tests":
        return python_tests(
            workspace_root=arguments["workspace_root"],
            target_relative=arguments.get("target_relative", "."),
            framework=arguments.get("framework", "auto"),
            arguments=arguments.get("arguments"),
            runtime_root=arguments.get("runtime_root"),
            python_selection=arguments.get("python_selection", "compatible"),
            python_executable=arguments.get("python_executable"),
            interpreter_relative=arguments.get("interpreter_relative"),
            timeout_seconds=arguments.get("timeout_seconds", 300),
        )
    if name == "kerr_qnm_jsonl_probe":
        return jsonl_probe(
            workspace_root=arguments["workspace_root"],
            language=arguments["language"],
            script_relative=arguments["script_relative"],
            messages=arguments["messages"],
            arguments=arguments.get("arguments"),
            project_relative=arguments.get("project_relative"),
            depot_path=arguments.get("depot_path"),
            use_managed_depot=arguments.get("use_managed_depot", False),
            runtime_root=arguments.get("runtime_root"),
            julia_selection=arguments.get("julia_selection", "compatible"),
            julia_executable=arguments.get("julia_executable"),
            python_selection=arguments.get("python_selection", "compatible"),
            python_executable=arguments.get("python_executable"),
            interpreter_relative=arguments.get("interpreter_relative"),
            strict_count=arguments.get("strict_count", True),
            timeout_seconds=arguments.get("timeout_seconds", 120),
        )
    if name == "kerr_qnm_numerical_canary":
        return numerical_canary(
            mode=arguments.get("mode", "all"),
            runtime_root=arguments.get("runtime_root"),
            julia_selection=arguments.get("julia_selection", "pinned"),
            julia_executable=arguments.get("julia_executable"),
            python_selection=arguments.get("python_selection", "managed"),
            python_executable=arguments.get("python_executable"),
            timeout_seconds=arguments.get("timeout_seconds", 120),
        )
    raise ToolkitError(f"Unknown tool: {name}")


def _text_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False)}],
        "isError": is_error,
    }


def _response(message_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id}
    if error is None:
        body["result"] = result
    else:
        body["error"] = error
    return body


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")
    notification = "id" not in message
    params = message.get("params", {})
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        requested = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol = requested if isinstance(requested, str) else "2024-11-05"
        return _response(
            message_id,
            {
                "protocolVersion": protocol,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )
    if method == "ping":
        return None if notification else _response(message_id, {})
    if method == "tools/list":
        return _response(message_id, {"tools": tool_definitions()})
    if method == "tools/call":
        try:
            if not isinstance(params, dict) or not isinstance(params.get("name"), str):
                raise ToolkitError("tools/call requires a string name.")
            value = call_tool(params["name"], _arguments(params))
            return _response(message_id, _text_result(value))
        except (ToolkitError, KeyError, TypeError, ValueError) as exc:
            return _response(message_id, _text_result({"ok": False, "error": str(exc)}, is_error=True))
    if notification:
        return None
    return _response(message_id, error={"code": -32601, "message": f"Method not found: {method}"})


def main() -> int:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("MCP messages must be JSON objects.")
            result = handle(message)
        except Exception as exc:
            result = _response(None, error={"code": -32700, "message": str(exc)})
        if result is not None:
            sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
