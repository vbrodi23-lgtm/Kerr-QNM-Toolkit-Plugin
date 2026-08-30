#!/usr/bin/env python3
"""Command-line bridge from Codex Cloud to the local Kerr QNM runtime."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from toolkit_runtime import runtime, workspace  # noqa: E402


def _json_array(value: str, label: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"{label} must be valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise argparse.ArgumentTypeError(f"{label} must contain a JSON array")
    return parsed


def _messages(value: str) -> list[Any]:
    return _json_array(value, "--messages-json")


def _add_workspace(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace-root", required=True, help="Absolute path to the checked-out solver repository")


def _add_runtime(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--runtime-root", help="Absolute managed-toolchain directory; defaults beneath the current user's home")


def _add_timeout(parser: argparse.ArgumentParser, default: int = 120) -> None:
    parser.add_argument("--timeout-seconds", type=int, default=default, help="Bounded subprocess timeout (1-1800)")


def _add_julia(parser: argparse.ArgumentParser) -> None:
    _add_runtime(parser)
    parser.add_argument("--julia-selection", choices=("compatible", "pinned", "system"), default="compatible")
    parser.add_argument("--julia-executable", help="Explicit absolute Julia executable")


def _add_python(parser: argparse.ArgumentParser) -> None:
    _add_runtime(parser)
    parser.add_argument("--python-selection", choices=("compatible", "managed", "system"), default="compatible")
    parser.add_argument("--python-executable", help="Explicit absolute Python executable")
    parser.add_argument("--interpreter-relative", help="Workspace-relative interpreter, for example .venv/bin/python")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run bounded Julia, Python, NumPy, SciPy, Git, workspace, and cross-language operations in a Codex Cloud checkout.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    current = subparsers.add_parser("toolchain-status", help="Inspect managed and compatible runtimes")
    _add_runtime(current)
    current.add_argument("--verify-assets", action="store_true")

    current = subparsers.add_parser("prepare-toolchain", help="Install the verified bundled Julia/Python toolchain")
    _add_runtime(current)
    current.add_argument("--install-julia", action=argparse.BooleanOptionalAction, default=True)
    current.add_argument("--install-python", action=argparse.BooleanOptionalAction, default=True)
    current.add_argument("--seed-julia-depot", action=argparse.BooleanOptionalAction, default=True)

    current = subparsers.add_parser("inspect-workspace", help="Discover Julia/Python projects, tests, notebooks, data, and Git state")
    _add_workspace(current)
    current.add_argument("--max-depth", type=int, default=6)
    current.add_argument("--max-files", type=int, default=5000)

    current = subparsers.add_parser("git-inspect", help="Report branch, commit, changes, submodules, and scrubbed remotes")
    _add_workspace(current)

    current = subparsers.add_parser("list-files", help="List contained workspace files")
    _add_workspace(current)
    current.add_argument("--path-relative", default=".")
    current.add_argument("--glob", default="**/*")
    current.add_argument("--max-files", type=int, default=1000)

    current = subparsers.add_parser("read-text", help="Read one contained UTF-8 text file")
    _add_workspace(current)
    current.add_argument("--path-relative", required=True)
    current.add_argument("--max-chars", type=int, default=120000)

    current = subparsers.add_parser("search-text", help="Search contained source files using literal text")
    _add_workspace(current)
    current.add_argument("--query", required=True)
    current.add_argument("--path-relative", default=".")
    current.add_argument("--glob", default="**/*")
    current.add_argument("--case-sensitive", action="store_true")
    current.add_argument("--max-results", type=int, default=200)

    current = subparsers.add_parser("git-diff", help="Show a bounded Git diff")
    _add_workspace(current)
    current.add_argument("--path-relative", default=".")
    current.add_argument("--staged", action="store_true")

    current = subparsers.add_parser("apply-patch", help="Validate and apply a unified Git patch from a file")
    _add_workspace(current)
    current.add_argument("--patch-relative", required=True, help="Workspace-relative path to a UTF-8 unified diff")
    current.add_argument("--allow-deletes", action="store_true")

    current = subparsers.add_parser("run-julia", help="Run an existing Julia file beneath the workspace")
    _add_workspace(current)
    _add_julia(current)
    _add_timeout(current)
    current.add_argument("--script-relative", required=True)
    current.add_argument("--argument", action="append", default=[])
    current.add_argument("--project-relative")
    current.add_argument("--depot-path")
    current.add_argument("--use-managed-depot", action="store_true")
    current.add_argument("--threads", type=int, default=1)
    current.add_argument("--offline", action="store_true")

    current = subparsers.add_parser("run-python", help="Run an existing Python file beneath the workspace")
    _add_workspace(current)
    _add_python(current)
    _add_timeout(current)
    current.add_argument("--script-relative", required=True)
    current.add_argument("--argument", action="append", default=[])
    current.add_argument("--isolated", action="store_true")

    current = subparsers.add_parser("julia-project", help="Run status, instantiate, precompile, resolve, or test")
    _add_workspace(current)
    _add_julia(current)
    _add_timeout(current, 300)
    current.add_argument("--project-relative", default=".")
    current.add_argument("--action", choices=("status", "instantiate", "precompile", "resolve", "test"), required=True)
    current.add_argument("--depot-path")
    current.add_argument("--use-managed-depot", action="store_true")
    current.add_argument("--allow-network", action="store_true")
    current.add_argument("--threads", type=int, default=1)

    current = subparsers.add_parser("python-tests", help="Run pytest or unittest beneath the workspace")
    _add_workspace(current)
    _add_python(current)
    _add_timeout(current, 300)
    current.add_argument("--target-relative", default=".")
    current.add_argument("--framework", choices=("auto", "pytest", "unittest"), default="auto")
    current.add_argument("--argument", action="append", default=[])

    current = subparsers.add_parser("jsonl-probe", help="Probe an existing Julia or Python JSON Lines worker")
    _add_workspace(current)
    _add_runtime(current)
    _add_timeout(current)
    current.add_argument("--language", choices=("julia", "python"), required=True)
    current.add_argument("--script-relative", required=True)
    current.add_argument("--messages-json", type=_messages, required=True, help="JSON array of messages")
    current.add_argument("--argument", action="append", default=[])
    current.add_argument("--project-relative")
    current.add_argument("--depot-path")
    current.add_argument("--use-managed-depot", action="store_true")
    current.add_argument("--julia-selection", choices=("compatible", "pinned", "system"), default="compatible")
    current.add_argument("--julia-executable")
    current.add_argument("--python-selection", choices=("compatible", "managed", "system"), default="compatible")
    current.add_argument("--python-executable")
    current.add_argument("--interpreter-relative")
    current.add_argument("--no-strict-count", action="store_true")

    current = subparsers.add_parser("numerical-canary", help="Run short deterministic Julia, NumPy/SciPy, and transfer checks")
    _add_timeout(current)
    _add_runtime(current)
    current.add_argument("--mode", choices=("all", "python", "julia", "cross-language"), default="all")
    current.add_argument("--julia-selection", choices=("compatible", "pinned", "system"), default="pinned")
    current.add_argument("--julia-executable")
    current.add_argument("--python-selection", choices=("compatible", "managed", "system"), default="managed")
    current.add_argument("--python-executable")
    return parser


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    command = args.command
    if command == "toolchain-status":
        return runtime.toolchain_status(args.runtime_root, args.verify_assets)
    if command == "prepare-toolchain":
        return runtime.prepare_toolchain(args.runtime_root, args.install_julia, args.install_python, args.seed_julia_depot)
    if command == "inspect-workspace":
        return runtime.inspect_workspace(args.workspace_root, args.max_depth, args.max_files)
    if command == "git-inspect":
        return runtime.git_inspect(args.workspace_root)
    if command == "list-files":
        return workspace.list_files(args.workspace_root, args.path_relative, args.glob, args.max_files)
    if command == "read-text":
        return workspace.read_text_file(args.workspace_root, args.path_relative, args.max_chars)
    if command == "search-text":
        return workspace.search_text(args.workspace_root, args.query, args.path_relative, args.glob, args.case_sensitive, args.max_results)
    if command == "git-diff":
        return workspace.git_diff(args.workspace_root, args.path_relative, args.staged)
    if command == "apply-patch":
        root = workspace.workspace_root(args.workspace_root)
        patch_path = runtime._workspace_path(root, args.patch_relative, "patch_relative")
        return workspace.apply_patch(args.workspace_root, patch_path.read_text(encoding="utf-8"), args.allow_deletes)
    if command == "run-julia":
        return runtime.run_julia_file(
            workspace_root=args.workspace_root, script_relative=args.script_relative, arguments=args.argument,
            project_relative=args.project_relative, depot_path=args.depot_path, use_managed_depot=args.use_managed_depot,
            runtime_root=args.runtime_root, julia_selection=args.julia_selection, julia_executable=args.julia_executable,
            threads=args.threads, offline=args.offline, timeout_seconds=args.timeout_seconds,
        )
    if command == "run-python":
        return runtime.run_python_file(
            workspace_root=args.workspace_root, script_relative=args.script_relative, arguments=args.argument,
            runtime_root=args.runtime_root, python_selection=args.python_selection, python_executable=args.python_executable,
            interpreter_relative=args.interpreter_relative, isolated=args.isolated, timeout_seconds=args.timeout_seconds,
        )
    if command == "julia-project":
        return runtime.julia_project_action(
            workspace_root=args.workspace_root, project_relative=args.project_relative, action=args.action,
            depot_path=args.depot_path, use_managed_depot=args.use_managed_depot, runtime_root=args.runtime_root,
            julia_selection=args.julia_selection, julia_executable=args.julia_executable, allow_network=args.allow_network,
            threads=args.threads, timeout_seconds=args.timeout_seconds,
        )
    if command == "python-tests":
        return runtime.python_tests(
            workspace_root=args.workspace_root, target_relative=args.target_relative, framework=args.framework,
            arguments=args.argument, runtime_root=args.runtime_root, python_selection=args.python_selection,
            python_executable=args.python_executable, interpreter_relative=args.interpreter_relative,
            timeout_seconds=args.timeout_seconds,
        )
    if command == "jsonl-probe":
        return runtime.jsonl_probe(
            workspace_root=args.workspace_root, language=args.language, script_relative=args.script_relative,
            messages=args.messages_json, arguments=args.argument, project_relative=args.project_relative,
            depot_path=args.depot_path, use_managed_depot=args.use_managed_depot, runtime_root=args.runtime_root,
            julia_selection=args.julia_selection, julia_executable=args.julia_executable,
            python_selection=args.python_selection, python_executable=args.python_executable,
            interpreter_relative=args.interpreter_relative, strict_count=not args.no_strict_count,
            timeout_seconds=args.timeout_seconds,
        )
    if command == "numerical-canary":
        return runtime.numerical_canary(
            mode=args.mode, runtime_root=args.runtime_root, julia_selection=args.julia_selection,
            julia_executable=args.julia_executable, python_selection=args.python_selection,
            python_executable=args.python_executable, timeout_seconds=args.timeout_seconds,
        )
    raise runtime.ToolkitError(f"Unknown command: {command}")


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        result = _dispatch(args)
    except (runtime.ToolkitError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
