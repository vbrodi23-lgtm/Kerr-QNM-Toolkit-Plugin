"""Bounded local execution helpers for the Kerr QNM Toolkit MCP server."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Iterable


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SEED_ROOT = PLUGIN_ROOT / "runtime-seed"
FIXTURE_ROOT = PLUGIN_ROOT / "fixtures"
POLICY_PATH = SEED_ROOT / "toolchain-policy.json"


class ToolkitError(RuntimeError):
    """A user-actionable failure from a toolkit operation."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ToolkitError(f"Required plugin asset is absent: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ToolkitError(f"Required plugin asset is malformed JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ToolkitError(f"Required JSON asset must contain an object: {path}")
    return value


POLICY = _read_json(POLICY_PATH)
JULIA_POLICY = POLICY["julia"]
PYTHON_POLICY = POLICY["python"]
PACKAGE_POLICY = {item["name"]: item for item in POLICY["python_packages"]}
DEPOT_POLICY = POLICY["julia_depot_seed"]
JULIA_VERSION = str(JULIA_POLICY["version"])
PYTHON_VERSION = str(PYTHON_POLICY["version"])
NUMPY_VERSION = str(PACKAGE_POLICY["numpy"]["version"])
SCIPY_VERSION = str(PACKAGE_POLICY["scipy"]["version"])


def _is_within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _absolute_path(value: Any, label: str, *, must_exist: bool) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ToolkitError(f"{label} must be a non-empty absolute path.")
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raise ToolkitError(f"{label} must be absolute: {value}")
    try:
        resolved = raw.resolve(strict=must_exist)
    except FileNotFoundError as exc:
        raise ToolkitError(f"{label} does not exist: {raw}") from exc
    if resolved == Path(resolved.anchor):
        raise ToolkitError(f"{label} must not be the filesystem root.")
    return resolved


def _runtime_root(value: str | None) -> Path:
    configured = value or os.environ.get("KERR_QNM_TOOLKIT_RUNTIME")
    if configured is None:
        configured = str(Path.home() / ".local" / "share" / "kerr-qnm-toolkit" / "runtime-1")
    return _absolute_path(configured, "runtime_root", must_exist=False)


def _workspace_path(root: Path, relative: Any, label: str, *, must_exist: bool = True) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ToolkitError(f"{label} must be a non-empty path relative to workspace_root.")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise ToolkitError(f"{label} must stay beneath workspace_root: {relative}")
    try:
        resolved = (root / raw).resolve(strict=must_exist)
    except FileNotFoundError as exc:
        raise ToolkitError(f"{label} does not exist: {relative}") from exc
    if not _is_within(root, resolved):
        raise ToolkitError(f"{label} resolves outside workspace_root: {relative}")
    return resolved


def _bounded_timeout(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1800:
        raise ToolkitError("timeout_seconds must be an integer from 1 through 1800.")
    return value


def _bounded_integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ToolkitError(f"{label} must be an integer from {minimum} through {maximum}.")
    return value


def _string_list(value: Any, label: str, *, maximum_items: int = 64) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ToolkitError(f"{label} must be a list of at most {maximum_items} strings.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or len(item) > 4096 or "\x00" in item:
            raise ToolkitError(f"Each {label} entry must be a string no longer than 4096 characters without NUL bytes.")
        result.append(item)
    return result


def _clip(value: str, maximum: int = 60_000) -> str:
    if len(value) <= maximum:
        return value
    omitted = len(value) - maximum
    return f"{value[:maximum]}\n… [truncated {omitted} characters]"


def _run(
    command: list[str],
    *,
    cwd: Path | None,
    env: dict[str, str] | None,
    timeout: int,
    input_text: str | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            input=input_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ToolkitError(f"Could not start executable: {command[0]}") from exc
    except OSError as exc:
        raise ToolkitError(f"Could not start executable {command[0]}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", "replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        return {
            "ok": False,
            "timed_out": True,
            "exit_code": None,
            "command": command,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": _clip(stdout),
            "stderr": _clip(stderr),
        }
    return {
        "ok": completed.returncode == 0,
        "timed_out": False,
        "exit_code": completed.returncode,
        "command": command,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout": _clip(completed.stdout),
        "stderr": _clip(completed.stderr),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _asset_entries() -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {
        "julia_archive": {"filename": JULIA_POLICY["archive"], "sha256": JULIA_POLICY["sha256"]},
        "cpython_archive": {"filename": PYTHON_POLICY["archive"], "sha256": PYTHON_POLICY["sha256"]},
        "julia_depot_seed": {"filename": DEPOT_POLICY["archive"], "sha256": DEPOT_POLICY["sha256"]},
    }
    for name, package in PACKAGE_POLICY.items():
        entries[f"{name}_wheel"] = {"filename": package["wheel"], "sha256": package["wheel_sha256"]}
        entries[f"{name}_source"] = {"filename": package["source_archive"], "sha256": package["source_sha256"]}
    return entries


def _asset_status(label: str, *, verify: bool) -> dict[str, Any]:
    entry = _asset_entries()[label]
    path = SEED_ROOT / str(entry["filename"])
    result: dict[str, Any] = {
        "path": str(path),
        "exists": path.is_file(),
        "expected_sha256": str(entry["sha256"]).lower(),
    }
    if path.is_file():
        result["bytes"] = path.stat().st_size
        if verify:
            result["sha256"] = _sha256_file(path)
            result["valid"] = result["sha256"] == result["expected_sha256"]
    elif verify:
        result["valid"] = False
    return result


def _verified_asset(label: str) -> Path:
    status = _asset_status(label, verify=True)
    if not status.get("exists"):
        raise ToolkitError(f"Packaged asset is absent: {status['path']}")
    if not status.get("valid"):
        raise ToolkitError(f"Packaged asset failed its SHA-256 check: {status['path']}")
    return Path(status["path"])


def _safe_extract_tar(archive: Path, destination: Path) -> None:
    destination = destination.resolve(strict=True)
    with tarfile.open(archive, mode="r:gz") as source:
        members = source.getmembers()
        for member in members:
            member_path = (destination / member.name).resolve(strict=False)
            if not _is_within(destination, member_path):
                raise ToolkitError(f"Refusing unsafe archive member path: {member.name}")
            if member.isdev():
                raise ToolkitError(f"Refusing device entry in archive: {member.name}")
            if member.issym() or member.islnk():
                link_base = member_path.parent if member.issym() else destination
                link_target = (link_base / member.linkname).resolve(strict=False)
                if Path(member.linkname).is_absolute() or not _is_within(destination, link_target):
                    raise ToolkitError(f"Refusing unsafe archive link: {member.name}")
        source.extractall(destination, members=members)
    _restore_tar_execute_bits(archive, destination)


def _restore_tar_execute_bits(archive: Path, destination: Path, archive_prefix: str | None = None) -> int:
    """Restore executable bits that some managed filesystems omit during extraction."""
    destination = destination.resolve(strict=True)
    prefix = Path(archive_prefix) if archive_prefix else None
    restored = 0
    with tarfile.open(archive, mode="r:gz") as source:
        for member in source.getmembers():
            if not member.isfile() or not member.mode & 0o111:
                continue
            member_path = Path(member.name)
            if prefix is not None:
                try:
                    member_path = member_path.relative_to(prefix)
                except ValueError:
                    continue
            target = (destination / member_path).resolve(strict=False)
            if _is_within(destination, target) and target.is_file():
                target.chmod(target.stat().st_mode | (member.mode & 0o111))
                restored += 1
    return restored


def _write_json_atomically(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _make_executable(path: Path, label: str) -> None:
    if not path.is_file():
        raise ToolkitError(f"Verified archive has no expected {label}: {path}")
    path.chmod(path.stat().st_mode | 0o111)


def _version_tuple(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def _managed_python_paths(root: Path) -> tuple[Path, Path]:
    base = root / "cpython" / PYTHON_VERSION / "bin" / "python3"
    environment = root / "python-env" / f"cpython-{PYTHON_VERSION}-numpy-{NUMPY_VERSION}-scipy-{SCIPY_VERSION}"
    return base, environment / "bin" / "python"


def _probe_julia(command: list[str]) -> dict[str, Any]:
    version_result = _run(command + ["--version"], cwd=None, env=None, timeout=15)
    if not version_result["ok"]:
        return {"valid": False, "reason": "version probe failed", "process": version_result}
    version_text = version_result["stdout"].strip()
    version = _version_tuple(version_text)
    bits_result = _run(
        command + ["--startup-file=no", "--history-file=no", "-e", "print(Sys.WORD_SIZE)"],
        cwd=None,
        env=None,
        timeout=15,
    )
    bits = int(bits_result["stdout"].strip()) if bits_result["ok"] and bits_result["stdout"].strip().isdigit() else None
    return {
        "valid": version is not None and bits == 64,
        "version": ".".join(str(part) for part in version) if version else None,
        "version_tuple": list(version) if version else None,
        "word_size": bits,
        "version_text": version_text,
    }


def _julia_candidates(root: Path, explicit: str | None) -> Iterable[tuple[str, list[str]]]:
    if explicit is not None:
        path = _absolute_path(explicit, "julia_executable", must_exist=True)
        yield "explicit", [str(path)]
        return
    configured = os.environ.get("KERR_QNM_JULIA")
    if configured:
        path = _absolute_path(configured, "KERR_QNM_JULIA", must_exist=True)
        yield "environment", [str(path)]
    yield "managed", [str(root / "julia" / JULIA_VERSION / "bin" / "julia")]
    system = shutil.which("julia")
    if system:
        yield "system", [system]
    juliaup = shutil.which("juliaup")
    if juliaup:
        yield "juliaup", [juliaup, "run", JULIA_VERSION]


def discover_julia(
    runtime_root: str | None = None,
    selection: str = "compatible",
    executable: str | None = None,
) -> dict[str, Any]:
    if selection not in {"pinned", "compatible", "any"}:
        raise ToolkitError("julia_selection must be pinned, compatible, or any.")
    root = _runtime_root(runtime_root)
    expected = _version_tuple(JULIA_VERSION)
    attempts: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for source, command in _julia_candidates(root, executable):
        if tuple(command) in seen:
            continue
        seen.add(tuple(command))
        if not Path(command[0]).is_file():
            attempts.append({"source": source, "command": command, "available": False})
            continue
        probe = _probe_julia(command)
        version = tuple(probe.get("version_tuple") or ())
        accepted = bool(probe.get("valid"))
        if accepted and selection == "pinned":
            accepted = version == expected
        elif accepted and selection == "compatible":
            accepted = len(version) == 3 and (1, 10, 0) <= version < (2, 0, 0)
        if accepted:
            return {"source": source, "command": command, "selection": selection, **probe}
        attempts.append({"source": source, "command": command, "available": True, **probe})
    raise ToolkitError(f"No {selection} 64-bit Julia runtime was found. Inspected: {json.dumps(attempts)}")


def _probe_python(executable: Path) -> dict[str, Any]:
    if not executable.is_file():
        return {"valid": False, "reason": f"Python executable is absent: {executable}"}
    source = (
        "import json,platform,struct,sys\n"
        "d={'python_version':platform.python_version(),'bits':struct.calcsize('P')*8,'executable':sys.executable}\n"
        "for n in ('numpy','scipy'):\n"
        " try:\n"
        "  m=__import__(n); d[n+'_version']=m.__version__\n"
        " except Exception as e: d[n+'_error']=type(e).__name__+': '+str(e)\n"
        "print(json.dumps(d,sort_keys=True))\n"
    )
    process = _run(
        [str(executable), "-c", source],
        cwd=None,
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
        timeout=30,
    )
    if not process["ok"]:
        return {"valid": False, "process": process}
    try:
        identity = json.loads(process["stdout"])
    except json.JSONDecodeError:
        return {"valid": False, "reason": "Python identity output was not JSON", "process": process}
    version = _version_tuple(str(identity.get("python_version", "")))
    return {
        "valid": version is not None and identity.get("bits") == 64,
        "version_tuple": list(version) if version else None,
        "identity": identity,
    }


def _python_candidates(root: Path, explicit: str | None, selection: str) -> Iterable[tuple[str, Path]]:
    if explicit is not None:
        yield "explicit", _absolute_path(explicit, "python_executable", must_exist=True)
        return
    configured = os.environ.get("KERR_QNM_PYTHON")
    if configured:
        yield "environment", _absolute_path(configured, "KERR_QNM_PYTHON", must_exist=True)
    _, managed = _managed_python_paths(root)
    yield "managed", managed
    if selection != "managed":
        yield "server", Path(sys.executable).resolve()
        system = shutil.which("python3")
        if system:
            yield "system", Path(system).resolve()


def discover_python(
    runtime_root: str | None = None,
    selection: str = "compatible",
    executable: str | None = None,
) -> dict[str, Any]:
    if selection not in {"managed", "compatible", "any"}:
        raise ToolkitError("python_selection must be managed, compatible, or any.")
    root = _runtime_root(runtime_root)
    expected = _version_tuple(PYTHON_VERSION)
    attempts: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for source, path in _python_candidates(root, executable, selection):
        if path in seen:
            continue
        seen.add(path)
        probe = _probe_python(path)
        version = tuple(probe.get("version_tuple") or ())
        identity = probe.get("identity", {})
        accepted = bool(probe.get("valid"))
        if accepted and selection == "managed":
            accepted = (
                source in {"explicit", "environment", "managed"}
                and version == expected
                and identity.get("numpy_version") == NUMPY_VERSION
                and identity.get("scipy_version") == SCIPY_VERSION
            )
        elif accepted and selection == "compatible":
            accepted = len(version) == 3 and (3, 10, 0) <= version < (4, 0, 0)
        if accepted:
            return {"source": source, "command": [str(path)], "selection": selection, **probe}
        attempts.append({"source": source, "path": str(path), **probe})
    raise ToolkitError(f"No {selection} 64-bit Python runtime was found. Inspected: {json.dumps(attempts)}")


def toolchain_status(runtime_root: str | None = None, verify_assets: bool = False) -> dict[str, Any]:
    if not isinstance(verify_assets, bool):
        raise ToolkitError("verify_assets must be a boolean.")
    root = _runtime_root(runtime_root)
    try:
        julia = discover_julia(str(root), "pinned")
    except ToolkitError as exc:
        julia = {"available": False, "error": str(exc)}
    try:
        python = discover_python(str(root), "managed")
    except ToolkitError as exc:
        python = {"available": False, "error": str(exc)}
    return {
        "ok": bool(julia.get("valid")) and bool(python.get("valid")),
        "profile_id": POLICY["profile_id"],
        "host": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "runtime_root": str(root),
        "expected": {
            "julia": JULIA_VERSION,
            "python": PYTHON_VERSION,
            "numpy": NUMPY_VERSION,
            "scipy": SCIPY_VERSION,
        },
        "managed_julia": julia,
        "managed_python": python,
        "julia_depot": {
            "path": str(root / "julia-depot"),
            "seeded": (root / "julia-depot" / ".kerr-qnm-toolkit-seed.json").is_file(),
        },
        "packaged_assets": {label: _asset_status(label, verify=verify_assets) for label in _asset_entries()},
        "assets_verified": verify_assets,
    }


def _provision_julia(root: Path) -> dict[str, Any]:
    executable = root / "julia" / JULIA_VERSION / "bin" / "julia"
    archive = _verified_asset("julia_archive")
    if executable.is_file():
        restored = _restore_tar_execute_bits(archive, executable.parents[1], f"julia-{JULIA_VERSION}")
        return {"reused": True, "restored_executables": restored, "runtime": discover_julia(str(root), "pinned")}
    destination = executable.parents[1]
    if destination.exists():
        raise ToolkitError(f"Julia destination exists but is incomplete: {destination}. Choose another runtime_root.")
    temporary_root = root / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="julia-extract-", dir=temporary_root) as temporary_text:
        staging = Path(temporary_text)
        _safe_extract_tar(archive, staging)
        extracted = staging / f"julia-{JULIA_VERSION}"
        _make_executable(extracted / "bin" / "julia", "Julia executable")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(extracted), str(destination))
    return {"reused": False, "runtime": discover_julia(str(root), "pinned")}


def _provision_python(root: Path) -> dict[str, Any]:
    base, environment = _managed_python_paths(root)
    if not base.is_file():
        archive = _verified_asset("cpython_archive")
        destination = base.parents[1]
        if destination.exists():
            raise ToolkitError(f"CPython destination exists but is incomplete: {destination}. Choose another runtime_root.")
        temporary_root = root / "tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="cpython-extract-", dir=temporary_root) as temporary_text:
            staging = Path(temporary_text)
            _safe_extract_tar(archive, staging)
            extracted = staging / "python"
            for name in ("python", "python3", "python3.12"):
                _make_executable(extracted / "bin" / name, f"CPython executable {name}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(extracted), str(destination))
    environment_root = environment.parents[1]
    created = False
    if not environment.is_file():
        if environment_root.exists():
            raise ToolkitError(f"Python environment exists but is incomplete: {environment_root}. Choose another runtime_root.")
        create = _run(
            [str(base), "-m", "venv", str(environment_root)],
            cwd=None,
            env={**os.environ, "PYTHONNOUSERSITE": "1"},
            timeout=120,
        )
        if not create["ok"]:
            raise ToolkitError(f"Could not create the managed Python environment: {create['stderr']}")
        created = True
    for label in ("numpy_wheel", "scipy_wheel"):
        _verified_asset(label)
    probe = _probe_python(environment)
    identity = probe.get("identity", {})
    if identity.get("numpy_version") != NUMPY_VERSION or identity.get("scipy_version") != SCIPY_VERSION:
        wheels = [str(SEED_ROOT / PACKAGE_POLICY[name]["wheel"]) for name in ("numpy", "scipy")]
        install = _run(
            [str(environment), "-m", "pip", "install", "--no-index", *wheels],
            cwd=None,
            env={**os.environ, "PYTHONNOUSERSITE": "1", "PIP_NO_INPUT": "1"},
            timeout=300,
        )
        if not install["ok"]:
            raise ToolkitError(f"Could not install bundled NumPy/SciPy wheels: {install['stderr']}")
    return {"created": created, "runtime": discover_python(str(root), "managed")}


def _seed_julia_depot(root: Path) -> dict[str, Any]:
    archive = _verified_asset("julia_depot_seed")
    expected_hash = str(DEPOT_POLICY["sha256"]).lower()
    destination = root / "julia-depot"
    receipt = destination / ".kerr-qnm-toolkit-seed.json"
    if receipt.is_file():
        existing = _read_json(receipt)
        if existing.get("archive_sha256") == expected_hash and (destination / "packages").is_dir():
            return {"path": str(destination), "reused": True}
    if destination.exists() and any(destination.iterdir()):
        raise ToolkitError(f"Refusing to alter non-empty Julia depot destination: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    _safe_extract_tar(archive, destination)
    if not (destination / "packages").is_dir():
        raise ToolkitError("The Julia depot seed has an unexpected layout: packages/ is absent.")
    _write_json_atomically(
        receipt,
        {
            "schema_version": 1,
            "archive_sha256": expected_hash,
            "archive_bytes": archive.stat().st_size,
            "seeded_by": "kerr-qnm-toolkit",
        },
    )
    return {"path": str(destination), "reused": False}


def prepare_toolchain(
    runtime_root: str | None = None,
    install_julia: bool = True,
    install_python: bool = True,
    seed_julia_depot: bool = True,
) -> dict[str, Any]:
    for label, value in {
        "install_julia": install_julia,
        "install_python": install_python,
        "seed_julia_depot": seed_julia_depot,
    }.items():
        if not isinstance(value, bool):
            raise ToolkitError(f"{label} must be a boolean.")
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "AMD64"}:
        raise ToolkitError("The bundled toolchain profile supports only 64-bit x86 Linux.")
    root = _runtime_root(runtime_root)
    if root.exists() and not root.is_dir():
        raise ToolkitError(f"runtime_root is not a directory: {root}")
    root.mkdir(parents=True, exist_ok=True)
    operations: dict[str, Any] = {}
    if install_julia:
        operations["julia"] = _provision_julia(root)
    if install_python:
        operations["python"] = _provision_python(root)
    if seed_julia_depot:
        operations["julia_depot"] = _seed_julia_depot(root)
    return {
        "ok": True,
        "runtime_root": str(root),
        "operations": operations,
        "status": toolchain_status(str(root), verify_assets=False),
    }


def _git_command(root: Path, arguments: list[str], timeout: int = 20) -> dict[str, Any]:
    git = shutil.which("git")
    if not git:
        raise ToolkitError("Git is not available on PATH.")
    return _run([git, "-C", str(root), *arguments], cwd=root, env=os.environ.copy(), timeout=timeout)


def _scrub_remote(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return "<unparseable remote>"
    if parsed.scheme and parsed.netloc:
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    if "@" in value and ":" in value:
        prefix, suffix = value.split("@", 1)
        if prefix != "git":
            return f"<credentials>@{suffix.split('?', 1)[0]}"
    return value.split("?", 1)[0].split("#", 1)[0]


def git_inspect(workspace_root: str) -> dict[str, Any]:
    root = _absolute_path(workspace_root, "workspace_root", must_exist=True)
    if not root.is_dir():
        raise ToolkitError(f"workspace_root is not a directory: {root}")
    if not shutil.which("git"):
        return {"available": False, "is_repository": False, "workspace_root": str(root)}
    top = _git_command(root, ["rev-parse", "--show-toplevel"])
    if not top["ok"]:
        return {"available": True, "is_repository": False, "workspace_root": str(root)}
    repository_root = Path(top["stdout"].strip()).resolve()
    commit = _git_command(root, ["rev-parse", "HEAD"])
    branch = _git_command(root, ["branch", "--show-current"])
    status = _git_command(root, ["status", "--short", "--branch"])
    porcelain = _git_command(root, ["status", "--porcelain=v1"])
    remote_names = _git_command(root, ["remote"])
    remotes: dict[str, list[str]] = {}
    if remote_names["ok"]:
        for name in [line.strip() for line in remote_names["stdout"].splitlines() if line.strip()]:
            urls = _git_command(root, ["remote", "get-url", "--all", name])
            if urls["ok"]:
                remotes[name] = [_scrub_remote(line) for line in urls["stdout"].splitlines() if line.strip()]
    submodules = _git_command(root, ["submodule", "status", "--recursive"], timeout=30)
    return {
        "available": True,
        "is_repository": True,
        "workspace_root": str(root),
        "repository_root": str(repository_root),
        "commit": commit["stdout"].strip() if commit["ok"] else None,
        "branch": branch["stdout"].strip() if branch["ok"] else None,
        "dirty": bool(porcelain["stdout"].strip()) if porcelain["ok"] else None,
        "status": status["stdout"],
        "remotes": remotes,
        "submodules": submodules["stdout"] if submodules["ok"] else None,
    }


def _toml_summary(path: Path, kind: str) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        return {"path": str(path), "error": str(exc)}
    if kind == "julia":
        return {
            "path": str(path),
            "name": value.get("name"),
            "uuid": value.get("uuid"),
            "version": value.get("version"),
            "dependencies": sorted((value.get("deps") or {}).keys()),
            "compat": value.get("compat") or {},
        }
    project = value.get("project") or {}
    return {
        "path": str(path),
        "name": project.get("name"),
        "version": project.get("version"),
        "requires_python": project.get("requires-python"),
        "dependencies": project.get("dependencies") or [],
        "build_system": value.get("build-system") or {},
    }


def inspect_workspace(workspace_root: str, max_depth: int = 6, max_files: int = 5000) -> dict[str, Any]:
    root = _absolute_path(workspace_root, "workspace_root", must_exist=True)
    if not root.is_dir():
        raise ToolkitError(f"workspace_root is not a directory: {root}")
    depth_limit = _bounded_integer(max_depth, "max_depth", 1, 12)
    file_limit = _bounded_integer(max_files, "max_files", 100, 20_000)
    ignored = {".git", ".hg", ".svn", ".venv", "venv", "node_modules", "__pycache__", ".julia", "julia-depot"}
    counts = {"julia": 0, "python": 0, "notebooks": 0, "toml": 0, "markdown": 0, "data": 0}
    julia_projects: list[dict[str, Any]] = []
    python_projects: list[dict[str, Any]] = []
    manifests: list[str] = []
    tests: list[str] = []
    workflows: list[str] = []
    entrypoints: list[str] = []
    scanned = 0
    truncated = False
    for directory_text, directory_names, file_names in os.walk(root):
        directory = Path(directory_text)
        relative_directory = directory.relative_to(root)
        depth = len(relative_directory.parts)
        directory_names[:] = sorted(name for name in directory_names if name not in ignored and depth < depth_limit)
        for filename in sorted(file_names):
            scanned += 1
            if scanned > file_limit:
                truncated = True
                break
            path = directory / filename
            relative = path.relative_to(root).as_posix()
            suffix = path.suffix.lower()
            if suffix == ".jl":
                counts["julia"] += 1
            elif suffix == ".py":
                counts["python"] += 1
            elif suffix == ".ipynb":
                counts["notebooks"] += 1
            elif suffix == ".toml":
                counts["toml"] += 1
            elif suffix in {".md", ".rst"}:
                counts["markdown"] += 1
            elif suffix in {".csv", ".tsv", ".json", ".h5", ".hdf5", ".jld2", ".npz", ".npy"}:
                counts["data"] += 1
            if filename == "Project.toml":
                summary = _toml_summary(path, "julia")
                summary["path"] = relative
                julia_projects.append(summary)
            elif filename == "pyproject.toml":
                summary = _toml_summary(path, "python")
                summary["path"] = relative
                python_projects.append(summary)
            if filename in {"Manifest.toml", "Manifest-v1.10.toml", "requirements.txt", "requirements-dev.txt", "environment.yml", "environment.yaml", "uv.lock", "poetry.lock", "Pipfile.lock"}:
                manifests.append(relative)
            if "test" in relative_directory.parts or "tests" in relative_directory.parts or filename.startswith("test_") or filename == "runtests.jl":
                if suffix in {".py", ".jl"}:
                    tests.append(relative)
            if relative.startswith(".github/workflows/") and suffix in {".yml", ".yaml"}:
                workflows.append(relative)
            if suffix in {".py", ".jl"} and any(token in filename.lower() for token in ("main", "run", "solve", "worker", "cli")):
                entrypoints.append(relative)
        if truncated:
            break
    git = git_inspect(str(root))
    return {
        "workspace_root": str(root),
        "scan": {"files_scanned": min(scanned, file_limit), "truncated": truncated, "max_depth": depth_limit},
        "file_counts": counts,
        "julia_projects": julia_projects,
        "python_projects": python_projects,
        "lockfiles_and_manifests": manifests[:100],
        "tests": tests[:200],
        "likely_entrypoints": entrypoints[:100],
        "github_workflows": workflows[:100],
        "git": git,
    }


def _julia_environment(root: Path, depot_path: str | None, runtime_root: str | None, use_managed_depot: bool) -> dict[str, str]:
    environment = os.environ.copy()
    environment["JULIA_PKG_PRECOMPILE_AUTO"] = "0"
    if depot_path is not None:
        depot = _absolute_path(depot_path, "depot_path", must_exist=True)
        if not depot.is_dir():
            raise ToolkitError(f"depot_path is not a directory: {depot}")
        environment["JULIA_DEPOT_PATH"] = str(depot)
    elif use_managed_depot:
        depot = _runtime_root(runtime_root) / "julia-depot"
        if not depot.is_dir():
            raise ToolkitError(f"Managed Julia depot is absent: {depot}")
        environment["JULIA_DEPOT_PATH"] = str(depot)
    return environment


def run_julia_file(
    *,
    workspace_root: str,
    script_relative: str,
    arguments: list[str] | None = None,
    project_relative: str | None = None,
    depot_path: str | None = None,
    use_managed_depot: bool = False,
    runtime_root: str | None = None,
    julia_selection: str = "compatible",
    julia_executable: str | None = None,
    threads: int = 1,
    offline: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    root = _absolute_path(workspace_root, "workspace_root", must_exist=True)
    if not root.is_dir():
        raise ToolkitError(f"workspace_root is not a directory: {root}")
    script = _workspace_path(root, script_relative, "script_relative")
    if not script.is_file():
        raise ToolkitError(f"script_relative is not a file: {script_relative}")
    timeout = _bounded_timeout(timeout_seconds)
    thread_count = _bounded_integer(threads, "threads", 1, 64)
    discovered = discover_julia(runtime_root, julia_selection, julia_executable)
    command = [*discovered["command"], "--startup-file=no", "--history-file=no", f"--threads={thread_count}"]
    if project_relative is not None:
        project = _workspace_path(root, project_relative, "project_relative")
        if not project.is_dir() or not (project / "Project.toml").is_file():
            raise ToolkitError("project_relative must be a directory containing Project.toml.")
        command.append(f"--project={project}")
    command.append(str(script))
    command.extend(_string_list(arguments, "arguments"))
    environment = _julia_environment(root, depot_path, runtime_root, use_managed_depot)
    if offline:
        environment["JULIA_PKG_OFFLINE"] = "true"
    result = _run(command, cwd=root, env=environment, timeout=timeout)
    result.update({"workspace_root": str(root), "julia": discovered})
    return result


def _selected_python(
    root: Path,
    runtime_root: str | None,
    selection: str,
    executable: str | None,
    interpreter_relative: str | None,
) -> dict[str, Any]:
    if executable is not None and interpreter_relative is not None:
        raise ToolkitError("Use only one of python_executable and interpreter_relative.")
    if interpreter_relative is not None:
        selected = _workspace_path(root, interpreter_relative, "interpreter_relative")
        if not selected.is_file():
            raise ToolkitError(f"interpreter_relative is not a file: {interpreter_relative}")
        executable = str(selected)
    return discover_python(runtime_root, selection, executable)


def run_python_file(
    *,
    workspace_root: str,
    script_relative: str,
    arguments: list[str] | None = None,
    runtime_root: str | None = None,
    python_selection: str = "compatible",
    python_executable: str | None = None,
    interpreter_relative: str | None = None,
    isolated: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    root = _absolute_path(workspace_root, "workspace_root", must_exist=True)
    if not root.is_dir():
        raise ToolkitError(f"workspace_root is not a directory: {root}")
    script = _workspace_path(root, script_relative, "script_relative")
    if not script.is_file():
        raise ToolkitError(f"script_relative is not a file: {script_relative}")
    discovered = _selected_python(root, runtime_root, python_selection, python_executable, interpreter_relative)
    command = [*discovered["command"], str(script), *_string_list(arguments, "arguments")]
    environment = os.environ.copy()
    if isolated:
        environment["PYTHONNOUSERSITE"] = "1"
    result = _run(command, cwd=root, env=environment, timeout=_bounded_timeout(timeout_seconds))
    result.update({"workspace_root": str(root), "python": discovered})
    return result


def julia_project_action(
    *,
    workspace_root: str,
    project_relative: str = ".",
    action: str,
    depot_path: str | None = None,
    use_managed_depot: bool = False,
    runtime_root: str | None = None,
    julia_selection: str = "compatible",
    julia_executable: str | None = None,
    allow_network: bool = False,
    threads: int = 1,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    if action not in {"status", "instantiate", "precompile", "resolve", "test"}:
        raise ToolkitError("action must be status, instantiate, precompile, resolve, or test.")
    root = _absolute_path(workspace_root, "workspace_root", must_exist=True)
    project = _workspace_path(root, project_relative, "project_relative")
    if not project.is_dir() or not (project / "Project.toml").is_file():
        raise ToolkitError("project_relative must be a directory containing Project.toml.")
    discovered = discover_julia(runtime_root, julia_selection, julia_executable)
    thread_count = _bounded_integer(threads, "threads", 1, 64)
    command = [
        *discovered["command"],
        "--startup-file=no",
        "--history-file=no",
        f"--threads={thread_count}",
        f"--project={project}",
        str(FIXTURE_ROOT / "julia_project_driver.jl"),
        action,
    ]
    environment = _julia_environment(root, depot_path, runtime_root, use_managed_depot)
    if not allow_network:
        environment["JULIA_PKG_OFFLINE"] = "true"
    result = _run(command, cwd=project, env=environment, timeout=_bounded_timeout(timeout_seconds))
    result.update({"workspace_root": str(root), "project": str(project), "action": action, "julia": discovered})
    return result


def python_tests(
    *,
    workspace_root: str,
    target_relative: str = ".",
    framework: str = "auto",
    arguments: list[str] | None = None,
    runtime_root: str | None = None,
    python_selection: str = "compatible",
    python_executable: str | None = None,
    interpreter_relative: str | None = None,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    if framework not in {"auto", "pytest", "unittest"}:
        raise ToolkitError("framework must be auto, pytest, or unittest.")
    root = _absolute_path(workspace_root, "workspace_root", must_exist=True)
    target = _workspace_path(root, target_relative, "target_relative")
    discovered = _selected_python(root, runtime_root, python_selection, python_executable, interpreter_relative)
    executable = discovered["command"][0]
    selected_framework = framework
    if framework == "auto":
        probe = _run([executable, "-c", "import pytest"], cwd=root, env=os.environ.copy(), timeout=20)
        selected_framework = "pytest" if probe["ok"] else "unittest"
    extras = _string_list(arguments, "arguments")
    if selected_framework == "pytest":
        command = [executable, "-m", "pytest", str(target), *extras]
    elif target.is_dir():
        command = [executable, "-m", "unittest", "discover", "-s", str(target), *extras]
    else:
        command = [executable, "-m", "unittest", "discover", "-s", str(target.parent), "-p", target.name, *extras]
    result = _run(
        command,
        cwd=root,
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
        timeout=_bounded_timeout(timeout_seconds),
    )
    result.update({"workspace_root": str(root), "target": str(target), "framework": selected_framework, "python": discovered})
    return result


def jsonl_probe(
    *,
    workspace_root: str,
    language: str,
    script_relative: str,
    messages: list[Any],
    arguments: list[str] | None = None,
    project_relative: str | None = None,
    depot_path: str | None = None,
    use_managed_depot: bool = False,
    runtime_root: str | None = None,
    julia_selection: str = "compatible",
    julia_executable: str | None = None,
    python_selection: str = "compatible",
    python_executable: str | None = None,
    interpreter_relative: str | None = None,
    strict_count: bool = True,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    if language not in {"julia", "python"}:
        raise ToolkitError("language must be julia or python.")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 32:
        raise ToolkitError("messages must contain from 1 through 32 JSON values.")
    if not isinstance(strict_count, bool):
        raise ToolkitError("strict_count must be a boolean.")
    encoded_lines: list[str] = []
    for message in messages:
        try:
            encoded_lines.append(json.dumps(message, ensure_ascii=False, separators=(",", ":")))
        except (TypeError, ValueError) as exc:
            raise ToolkitError(f"messages contains a value that cannot be encoded as JSON: {exc}") from exc
    input_text = "\n".join(encoded_lines) + "\n"
    if len(input_text.encode("utf-8")) > 1_048_576:
        raise ToolkitError("The encoded JSON Lines input exceeds 1 MiB.")
    root = _absolute_path(workspace_root, "workspace_root", must_exist=True)
    script = _workspace_path(root, script_relative, "script_relative")
    extras = _string_list(arguments, "arguments")
    runtime: dict[str, Any]
    environment = os.environ.copy()
    if language == "python":
        runtime = _selected_python(root, runtime_root, python_selection, python_executable, interpreter_relative)
        command = [*runtime["command"], str(script), *extras]
    else:
        runtime = discover_julia(runtime_root, julia_selection, julia_executable)
        command = [*runtime["command"], "--startup-file=no", "--history-file=no"]
        if project_relative is not None:
            project = _workspace_path(root, project_relative, "project_relative")
            if not project.is_dir() or not (project / "Project.toml").is_file():
                raise ToolkitError("project_relative must be a directory containing Project.toml.")
            command.append(f"--project={project}")
        command.extend([str(script), *extras])
        environment = _julia_environment(root, depot_path, runtime_root, use_managed_depot)
    process = _run(
        command,
        cwd=root,
        env=environment,
        timeout=_bounded_timeout(timeout_seconds),
        input_text=input_text,
    )
    responses: list[Any] = []
    parse_errors: list[dict[str, Any]] = []
    for index, line in enumerate(process["stdout"].splitlines()):
        if not line.strip():
            continue
        try:
            responses.append(json.loads(line))
        except json.JSONDecodeError as exc:
            parse_errors.append({"line": index + 1, "error": str(exc), "text": _clip(line, 1000)})
    framing_valid = process["ok"] and not parse_errors and (not strict_count or len(responses) == len(messages))
    return {
        "ok": framing_valid,
        "language": language,
        "input_count": len(messages),
        "response_count": len(responses),
        "responses": responses,
        "parse_errors": parse_errors,
        "strict_count": strict_count,
        "process": process,
        "runtime": runtime,
    }


def _load_output(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ToolkitError(f"{label} did not create its expected output file.")
    return _read_json(path)


def _validate_python_numerics(payload: dict[str, Any]) -> None:
    if payload.get("kind") != "kerr-qnm-python-numerics/v1":
        raise ToolkitError("Python numerical canary returned an unexpected contract kind.")
    solution = payload.get("linear_solution")
    if not isinstance(solution, list) or len(solution) != 2:
        raise ToolkitError("Python numerical canary returned an invalid linear solution.")
    checks = [
        abs(float(solution[0]) - 0.1) <= 1e-13,
        abs(float(solution[1]) - 0.6) <= 1e-13,
        float(payload["linear_residual_norm"]) <= 1e-13,
        abs(float(payload["sqrt_two"]) - 2.0**0.5) <= 1e-13,
        abs(float(payload["ode_exp_minus_one"]) - float(payload["reference_exp_minus_one"])) <= 1e-9,
        abs(float(payload["bessel_j0_zero"]) - 1.0) <= 1e-14,
        float(payload["fft_roundtrip_error"]) <= 1e-13,
    ]
    if not all(checks):
        raise ToolkitError("Python numerical canary failed a deterministic tolerance check.")


def _validate_julia_numerics(payload: dict[str, Any]) -> None:
    if payload.get("kind") != "kerr-qnm-julia-numerics/v1":
        raise ToolkitError("Julia numerical canary returned an unexpected contract kind.")
    solution = payload.get("linear_solution")
    complex_sqrt = payload.get("complex_sqrt")
    if not isinstance(solution, list) or len(solution) != 2 or not isinstance(complex_sqrt, list) or len(complex_sqrt) != 2:
        raise ToolkitError("Julia numerical canary returned an invalid payload shape.")
    checks = [
        abs(float(solution[0]) - 0.1) <= 1e-13,
        abs(float(solution[1]) - 0.6) <= 1e-13,
        float(payload["linear_residual_norm"]) <= 1e-13,
        abs(float(complex_sqrt[0]) - 2.0) <= 1e-13,
        abs(float(complex_sqrt[1]) - 1.0) <= 1e-13,
    ]
    if not all(checks):
        raise ToolkitError("Julia numerical canary failed a deterministic tolerance check.")


def numerical_canary(
    *,
    mode: str = "all",
    runtime_root: str | None = None,
    julia_selection: str = "pinned",
    julia_executable: str | None = None,
    python_selection: str = "managed",
    python_executable: str | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    if mode not in {"all", "python", "julia", "cross-language"}:
        raise ToolkitError("mode must be all, python, julia, or cross-language.")
    timeout = _bounded_timeout(timeout_seconds)
    need_python = mode in {"all", "python", "cross-language"}
    need_julia = mode in {"all", "julia", "cross-language"}
    python_runtime = discover_python(runtime_root, python_selection, python_executable) if need_python else None
    julia_runtime = discover_julia(runtime_root, julia_selection, julia_executable) if need_julia else None
    results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="kerr-qnm-canary-") as temporary_text:
        temporary = Path(temporary_text)
        python_output = temporary / "python-numerics.json"
        if need_python:
            python_process = _run(
                [*python_runtime["command"], str(FIXTURE_ROOT / "python_numerical_canary.py"), str(python_output)],
                cwd=PLUGIN_ROOT,
                env={**os.environ, "PYTHONNOUSERSITE": "1"},
                timeout=timeout,
            )
            if not python_process["ok"]:
                return {"ok": False, "mode": mode, "python_process": python_process, "python": python_runtime}
            python_payload = _load_output(python_output, "Python numerical canary")
            _validate_python_numerics(python_payload)
            results["python"] = {"process": python_process, "runtime": python_runtime, "contract": python_payload}
        julia_output = temporary / "julia-numerics.json"
        if mode in {"all", "julia"}:
            julia_process = _run(
                [
                    *julia_runtime["command"],
                    "--startup-file=no",
                    "--history-file=no",
                    str(FIXTURE_ROOT / "julia_numerical_canary.jl"),
                    str(julia_output),
                ],
                cwd=PLUGIN_ROOT,
                env=os.environ.copy(),
                timeout=timeout,
            )
            if not julia_process["ok"]:
                return {"ok": False, "mode": mode, **results, "julia_process": julia_process, "julia": julia_runtime}
            julia_payload = _load_output(julia_output, "Julia numerical canary")
            _validate_julia_numerics(julia_payload)
            results["julia"] = {"process": julia_process, "runtime": julia_runtime, "contract": julia_payload}
        if mode in {"all", "cross-language"}:
            cross_output = temporary / "cross-language.json"
            cross_process = _run(
                [
                    *julia_runtime["command"],
                    "--startup-file=no",
                    "--history-file=no",
                    str(FIXTURE_ROOT / "cross_language_probe.jl"),
                    str(python_output),
                    str(cross_output),
                ],
                cwd=PLUGIN_ROOT,
                env=os.environ.copy(),
                timeout=timeout,
            )
            if not cross_process["ok"]:
                return {"ok": False, "mode": mode, **results, "cross_language_process": cross_process}
            cross_payload = _load_output(cross_output, "Cross-language canary")
            source_bytes = python_output.read_bytes()
            expected = {
                "schema_version": 1,
                "kind": "kerr-qnm-cross-language/v1",
                "input_bytes": len(source_bytes),
                "input_sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
            if cross_payload != expected:
                raise ToolkitError("Cross-language canary failed its byte-for-byte transfer contract.")
            results["cross_language"] = {
                "process": cross_process,
                "julia_runtime": julia_runtime,
                "contract": cross_payload,
            }
    return {"ok": True, "mode": mode, **results}
