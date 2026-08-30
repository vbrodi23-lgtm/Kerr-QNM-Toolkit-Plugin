#!/usr/bin/env python3
"""Streamable-HTTP MCP service for a persistent remote Kerr QNM workspace."""

from __future__ import annotations

import os
from typing import Any, Literal

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from personal_oauth import (
    OAuthBearerGate,
    about_page,
    authorization_server_metadata,
    authorize,
    oauth_is_configured,
    protected_resource_metadata,
    token,
)
from toolkit_runtime import runtime
from toolkit_runtime.remote_workspace import apply_patch, configured_workspace_root, git_diff, list_files, read_text_file, search_text


SERVER_VERSION = "1.2.1"
READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)
EXECUTE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False)

mcp = MCPServer(
    "kerr-qnm-toolkit",
    title="Kerr QNM Toolkit",
    description="A persistent Linux Julia/Python workspace for developing, testing, and auditing Kerr black-hole QNM solvers.",
    instructions="Inspect before editing, preserve repository conventions, run bounded checks, and require direct user instruction for long or production numerical runs.",
    version=SERVER_VERSION,
)


def _root() -> str:
    return str(configured_workspace_root())


def _runtime_root() -> str | None:
    return os.environ.get("KERR_QNM_TOOLKIT_RUNTIME")


@mcp.custom_route("/healthz", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "kerr-qnm-toolkit", "version": SERVER_VERSION, "oauth_configured": oauth_is_configured()})


@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
@mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])
async def oauth_protected_resource(_: Request) -> JSONResponse:
    return protected_resource_metadata()


@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_metadata(_: Request) -> JSONResponse:
    return authorization_server_metadata()


@mcp.custom_route("/oauth/about", methods=["GET"])
async def oauth_about(_: Request) -> Response:
    return about_page()


@mcp.custom_route("/oauth/authorize", methods=["GET", "POST"])
async def oauth_authorize(request: Request) -> Response:
    return await authorize(request)


@mcp.custom_route("/oauth/token", methods=["POST"])
async def oauth_token(request: Request) -> Response:
    return await token(request)


@mcp.tool(title="Inspect toolchain", annotations=READ_ONLY)
def kerr_qnm_toolchain_status(verify_assets: bool = False) -> dict[str, Any]:
    """Report the container's Julia, Python, NumPy, SciPy, and bundled runtime state."""
    return runtime.toolchain_status(runtime_root=_runtime_root(), verify_assets=verify_assets)


@mcp.tool(title="Inspect solver workspace", annotations=READ_ONLY)
def kerr_qnm_inspect_workspace(max_depth: int = 6, max_files: int = 5000) -> dict[str, Any]:
    """Discover Julia/Python projects, tests, entry points, data, workflows, and Git state."""
    return runtime.inspect_workspace(_root(), max_depth=max_depth, max_files=max_files)


@mcp.tool(title="Inspect Git state", annotations=READ_ONLY)
def kerr_qnm_git_inspect() -> dict[str, Any]:
    """Report branch, commit, changes, submodules, and credential-scrubbed remotes."""
    return runtime.git_inspect(_root())


@mcp.tool(title="List workspace files", annotations=READ_ONLY)
def kerr_qnm_list_files(path_relative: str = ".", glob_pattern: str = "**/*", max_files: int = 1000) -> dict[str, Any]:
    """List files below a workspace directory without exposing container paths outside it."""
    return list_files(path_relative, glob_pattern, max_files)


@mcp.tool(title="Read source file", annotations=READ_ONLY)
def kerr_qnm_read_text_file(path_relative: str, max_chars: int = 120_000) -> dict[str, Any]:
    """Read a bounded UTF-8 source or text file and return its SHA-256 digest."""
    return read_text_file(path_relative, max_chars)


@mcp.tool(title="Search source text", annotations=READ_ONLY)
def kerr_qnm_search_text(query: str, path_relative: str = ".", glob_pattern: str = "**/*", case_sensitive: bool = False, max_results: int = 200) -> dict[str, Any]:
    """Search bounded text files below the workspace using a literal query."""
    return search_text(query, path_relative, glob_pattern, case_sensitive, max_results)


@mcp.tool(title="Show Git diff", annotations=READ_ONLY)
def kerr_qnm_git_diff(path_relative: str = ".", staged: bool = False) -> dict[str, Any]:
    """Return the current bounded Git diff for all or part of the solver workspace."""
    return git_diff(path_relative, staged)


@mcp.tool(title="Apply source patch", annotations=WRITE)
def kerr_qnm_apply_patch(patch: str, allow_deletes: bool = False) -> dict[str, Any]:
    """Validate and apply a unified Git patch inside the workspace; deletion requires an explicit flag."""
    return apply_patch(patch, allow_deletes)


@mcp.tool(title="Run Julia file", annotations=EXECUTE)
def kerr_qnm_run_julia_file(
    script_relative: str,
    arguments: list[str] | None = None,
    project_relative: str | None = None,
    threads: int = 1,
    offline: bool = True,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Run an existing Julia file with the managed Linux runtime and bounded resources."""
    return runtime.run_julia_file(
        workspace_root=_root(), script_relative=script_relative, arguments=arguments, project_relative=project_relative,
        use_managed_depot=True, runtime_root=_runtime_root(), julia_selection="pinned", threads=threads,
        offline=offline, timeout_seconds=timeout_seconds,
    )


@mcp.tool(title="Run Python file", annotations=EXECUTE)
def kerr_qnm_run_python_file(
    script_relative: str,
    arguments: list[str] | None = None,
    interpreter_relative: str | None = None,
    isolated: bool = True,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Run an existing Python file with the managed NumPy/SciPy environment or a project interpreter."""
    selection = "compatible" if interpreter_relative else "managed"
    return runtime.run_python_file(
        workspace_root=_root(), script_relative=script_relative, arguments=arguments, runtime_root=_runtime_root(),
        python_selection=selection, interpreter_relative=interpreter_relative, isolated=isolated,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool(title="Run Julia project action", annotations=EXECUTE)
def kerr_qnm_julia_project(
    action: Literal["status", "instantiate", "precompile", "resolve", "test"],
    project_relative: str = ".",
    allow_network: bool = False,
    threads: int = 1,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Inspect, instantiate, precompile, resolve, or test a Julia project in the workspace."""
    return runtime.julia_project_action(
        workspace_root=_root(), project_relative=project_relative, action=action, use_managed_depot=True,
        runtime_root=_runtime_root(), julia_selection="pinned", allow_network=allow_network,
        threads=threads, timeout_seconds=timeout_seconds,
    )


@mcp.tool(title="Run Python tests", annotations=EXECUTE)
def kerr_qnm_python_tests(
    target_relative: str = ".",
    framework: Literal["auto", "pytest", "unittest"] = "auto",
    arguments: list[str] | None = None,
    interpreter_relative: str | None = None,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Run pytest or unittest against an existing target with managed or project Python."""
    selection = "compatible" if interpreter_relative else "managed"
    return runtime.python_tests(
        workspace_root=_root(), target_relative=target_relative, framework=framework, arguments=arguments,
        runtime_root=_runtime_root(), python_selection=selection, interpreter_relative=interpreter_relative,
        timeout_seconds=timeout_seconds,
    )


@mcp.tool(title="Probe JSON Lines worker", annotations=EXECUTE)
def kerr_qnm_jsonl_probe(
    language: Literal["julia", "python"],
    script_relative: str,
    messages: list[Any],
    arguments: list[str] | None = None,
    project_relative: str | None = None,
    strict_count: bool = True,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Exercise an existing Julia or Python JSON Lines worker and validate response framing."""
    return runtime.jsonl_probe(
        workspace_root=_root(), language=language, script_relative=script_relative, messages=messages,
        arguments=arguments, project_relative=project_relative, use_managed_depot=True,
        runtime_root=_runtime_root(), julia_selection="pinned", python_selection="managed",
        strict_count=strict_count, timeout_seconds=timeout_seconds,
    )


@mcp.tool(title="Run numerical canary", annotations=EXECUTE)
def kerr_qnm_numerical_canary(
    mode: Literal["all", "python", "julia", "cross-language"] = "all",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    """Validate deterministic Julia/Python linear algebra, roots, ODEs, FFTs, and data transfer."""
    return runtime.numerical_canary(mode=mode, runtime_root=_runtime_root(), timeout_seconds=timeout_seconds)


def _transport_security() -> TransportSecuritySettings:
    hosts = [value.strip() for value in os.environ.get("KERR_QNM_ALLOWED_HOSTS", "localhost,localhost:*,127.0.0.1,127.0.0.1:*").split(",") if value.strip()]
    origins = [value.strip() for value in os.environ.get("KERR_QNM_ALLOWED_ORIGINS", "").split(",") if value.strip()]
    return TransportSecuritySettings(allowed_hosts=hosts, allowed_origins=origins)


app = OAuthBearerGate(
    mcp.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=_transport_security(),
    )
)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), proxy_headers=True)
