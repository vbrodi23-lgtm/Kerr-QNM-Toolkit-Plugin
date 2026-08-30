"""Bounded source operations for a local Codex Cloud checkout."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from .runtime import ToolkitError, _bounded_integer, _clip, _run, _workspace_path


_SKIP_DIRECTORIES = {".git", ".julia", ".venv", "__pycache__", "node_modules"}
_TEXT_SUFFIXES = {
    "",
    ".c",
    ".cfg",
    ".cpp",
    ".csv",
    ".h",
    ".ini",
    ".jl",
    ".json",
    ".md",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".tsv",
    ".txt",
    ".yaml",
    ".yml",
}


def workspace_root(value: str) -> Path:
    """Resolve an explicit non-root workspace directory."""

    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raise ToolkitError("workspace_root must be an absolute path.")
    try:
        root = raw.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ToolkitError(f"workspace_root does not exist: {raw}") from exc
    if root == Path(root.anchor):
        raise ToolkitError("workspace_root must not be the filesystem root.")
    if not root.is_dir():
        raise ToolkitError("workspace_root must be a directory.")
    return root


def _relative_file(workspace: str, relative: str, *, must_exist: bool = True) -> tuple[Path, Path]:
    root = workspace_root(workspace)
    path = _workspace_path(root, relative, "path_relative", must_exist=must_exist)
    return root, path


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def list_files(workspace: str, path_relative: str = ".", glob_pattern: str = "**/*", max_files: int = 1000) -> dict[str, Any]:
    root, base = _relative_file(workspace, path_relative)
    if not base.is_dir():
        raise ToolkitError("path_relative must identify a directory.")
    limit = _bounded_integer(max_files, "max_files", 1, 5000)
    if not isinstance(glob_pattern, str) or not glob_pattern or len(glob_pattern) > 256:
        raise ToolkitError("glob_pattern must be a non-empty string no longer than 256 characters.")
    matches: list[str] = []
    scanned = 0
    for path in base.rglob("*"):
        relative = path.relative_to(root)
        if any(part in _SKIP_DIRECTORIES for part in relative.parts):
            continue
        scanned += 1
        if path.is_file() and relative.match(glob_pattern):
            matches.append(relative.as_posix())
            if len(matches) >= limit:
                break
    return {"path": base.relative_to(root).as_posix(), "files": matches, "count": len(matches), "scanned": scanned, "truncated": len(matches) >= limit}


def read_text_file(workspace: str, path_relative: str, max_chars: int = 120_000) -> dict[str, Any]:
    root, path = _relative_file(workspace, path_relative)
    if not path.is_file():
        raise ToolkitError("path_relative must identify a file.")
    limit = _bounded_integer(max_chars, "max_chars", 1000, 250_000)
    if path.stat().st_size > 5_000_000:
        raise ToolkitError("Refusing to read a text file larger than 5 MB.")
    payload = path.read_bytes()
    if b"\x00" in payload:
        raise ToolkitError("The selected file appears to be binary.")
    text = payload.decode("utf-8", errors="replace")
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha256_bytes(payload),
        "characters": len(text),
        "truncated": len(text) > limit,
        "content": _clip(text, limit),
    }


def search_text(
    workspace: str,
    query: str,
    path_relative: str = ".",
    glob_pattern: str = "**/*",
    case_sensitive: bool = False,
    max_results: int = 200,
) -> dict[str, Any]:
    root, base = _relative_file(workspace, path_relative)
    if not base.is_dir():
        raise ToolkitError("path_relative must identify a directory.")
    if not isinstance(query, str) or not query or len(query) > 1000 or "\x00" in query:
        raise ToolkitError("query must contain 1 through 1000 characters without NUL bytes.")
    if not isinstance(glob_pattern, str) or not glob_pattern or len(glob_pattern) > 256:
        raise ToolkitError("glob_pattern must be a non-empty string no longer than 256 characters.")
    limit = _bounded_integer(max_results, "max_results", 1, 1000)
    flags = 0 if case_sensitive else re.IGNORECASE
    expression = re.compile(re.escape(query), flags)
    results: list[dict[str, Any]] = []
    files_scanned = 0
    for path in base.rglob("*"):
        relative = path.relative_to(root)
        if not path.is_file() or any(part in _SKIP_DIRECTORIES for part in relative.parts):
            continue
        if not relative.match(glob_pattern) or path.suffix.lower() not in _TEXT_SUFFIXES or path.stat().st_size > 2_000_000:
            continue
        payload = path.read_bytes()
        if b"\x00" in payload:
            continue
        files_scanned += 1
        for line_number, line in enumerate(payload.decode("utf-8", errors="replace").splitlines(), start=1):
            if expression.search(line):
                results.append({"path": relative.as_posix(), "line": line_number, "text": _clip(line, 500)})
                if len(results) >= limit:
                    return {"query": query, "matches": results, "count": len(results), "files_scanned": files_scanned, "truncated": True}
    return {"query": query, "matches": results, "count": len(results), "files_scanned": files_scanned, "truncated": False}


def git_diff(workspace: str, path_relative: str = ".", staged: bool = False) -> dict[str, Any]:
    root, selected = _relative_file(workspace, path_relative)
    command = ["git", "-C", str(root), "diff", "--no-ext-diff", "--no-color", "--unified=3"]
    if staged:
        command.append("--cached")
    command.extend(["--", str(selected.relative_to(root))])
    result = _run(command, cwd=root, env=os.environ.copy(), timeout=60)
    result.update({"path": selected.relative_to(root).as_posix(), "staged": staged})
    return result


def apply_patch(workspace: str, patch: str, allow_deletes: bool = False) -> dict[str, Any]:
    root = workspace_root(workspace)
    if not isinstance(patch, str) or not patch.strip() or "\x00" in patch:
        raise ToolkitError("patch must be non-empty UTF-8 unified-diff text without NUL bytes.")
    if len(patch.encode("utf-8")) > 1_048_576:
        raise ToolkitError("patch exceeds the 1 MiB limit.")
    if not (root / ".git").exists():
        raise ToolkitError("Patch application requires a Git workspace.")
    if not allow_deletes and ("+++ /dev/null" in patch or "deleted file mode " in patch):
        raise ToolkitError("The patch deletes files; repeat with allow_deletes=true only when deletion is intended.")
    paths: list[str] = []
    for line in patch.splitlines():
        if not line.startswith(("--- ", "+++ ")):
            continue
        raw = line[4:].split("\t", 1)[0]
        if raw == "/dev/null":
            continue
        relative = raw[2:] if raw.startswith(("a/", "b/")) else raw
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ToolkitError(f"Patch path must stay inside the workspace: {relative}")
        _workspace_path(root, relative, "patch path", must_exist=False)
        paths.append(candidate.as_posix())
    if not paths:
        raise ToolkitError("patch contains no recognized file headers.")
    check = _run(["git", "-C", str(root), "apply", "--check", "--whitespace=error-all", "-"], cwd=root, env=os.environ.copy(), timeout=60, input_text=patch)
    if not check["ok"]:
        return {"ok": False, "applied": False, "paths": sorted(set(paths)), "check": check}
    applied = _run(["git", "-C", str(root), "apply", "--whitespace=error-all", "-"], cwd=root, env=os.environ.copy(), timeout=60, input_text=patch)
    return {"ok": applied["ok"], "applied": applied["ok"], "paths": sorted(set(paths)), "process": applied}
