from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]

from toolkit_runtime import remote_workspace, runtime  # noqa: E402


class KerrQnmToolkitTests(unittest.TestCase):
    def test_all_packaged_assets_match_policy(self) -> None:
        for label in runtime._asset_entries():
            status = runtime._asset_status(label, verify=True)
            self.assertTrue(status["valid"], label)

    def test_public_text_has_no_retired_project_labels(self) -> None:
        rejected = (
            "m" + "02",
            "windows" + "_solver",
            "windows" + "-solver",
            "kerr" + "-julia-bridge",
        )
        suffixes = {".py", ".jl", ".json", ".md", ".yaml", ".yml", ".toml"}
        for path in PLUGIN_ROOT.rglob("*"):
            if path.is_file() and path.suffix.lower() in suffixes:
                text = path.read_text(encoding="utf-8", errors="replace").lower()
                for token in rejected:
                    self.assertNotIn(token, text, f"{token} appears in {path.relative_to(PLUGIN_ROOT)}")

    def test_workspace_path_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaises(runtime.ToolkitError):
                runtime._workspace_path(root, "../outside.jl", "script_relative")

    def test_remote_credentials_are_scrubbed(self) -> None:
        value = runtime._scrub_remote("https://user:secret@example.com/owner/repo.git?token=hidden")
        self.assertEqual(value, "https://example.com/owner/repo.git")

    @unittest.skipIf(os.name == "nt", "POSIX executable shim targets the Linux container")
    def test_discovery_accepts_pinned_julia_shim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            shim = Path(temporary) / "julia"
            shim.write_text(
                "#!/usr/bin/env python3\n"
                "import sys\n"
                f"print('julia version {runtime.JULIA_VERSION}' if '--version' in sys.argv else '64', end='')\n",
                encoding="utf-8",
            )
            shim.chmod(0o755)
            discovered = runtime.discover_julia(selection="pinned", executable=str(shim))
        self.assertEqual(discovered["source"], "explicit")
        self.assertEqual(discovered["version"], runtime.JULIA_VERSION)

    def test_workspace_inspection_is_project_neutral(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Project.toml").write_text(
                'name = "ExampleQNM"\nuuid = "00000000-0000-0000-0000-000000000001"\nversion = "0.1.0"\n[deps]\n',
                encoding="utf-8",
            )
            (root / "pyproject.toml").write_text(
                '[project]\nname = "example-qnm"\nversion = "0.1.0"\ndependencies = ["numpy"]\n',
                encoding="utf-8",
            )
            (root / "src").mkdir()
            (root / "src" / "solve.jl").write_text("println(1)\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_solver.py").write_text("pass\n", encoding="utf-8")
            report = runtime.inspect_workspace(str(root), max_depth=4, max_files=100)
        self.assertEqual(report["julia_projects"][0]["name"], "ExampleQNM")
        self.assertEqual(report["python_projects"][0]["name"], "example-qnm")
        self.assertIn("src/solve.jl", report["likely_entrypoints"])
        self.assertIn("tests/test_solver.py", report["tests"])

    def test_remote_workspace_read_list_and_search_are_contained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            source = root / "src"
            source.mkdir()
            (source / "solver.jl").write_text("function solve_mode(spin)\n    spin + 1\nend\n", encoding="utf-8")
            previous = os.environ.get("KERR_QNM_WORKSPACE_ROOT")
            os.environ["KERR_QNM_WORKSPACE_ROOT"] = str(root)
            try:
                listing = remote_workspace.list_files(".", "**/*.jl")
                read = remote_workspace.read_text_file("src/solver.jl")
                search = remote_workspace.search_text("solve_mode", glob_pattern="**/*.jl")
                with self.assertRaises(runtime.ToolkitError):
                    remote_workspace.read_text_file("../outside.txt")
            finally:
                if previous is None:
                    os.environ.pop("KERR_QNM_WORKSPACE_ROOT", None)
                else:
                    os.environ["KERR_QNM_WORKSPACE_ROOT"] = previous
        self.assertEqual(listing["files"], ["src/solver.jl"])
        self.assertIn("function solve_mode", read["content"])
        self.assertEqual(search["matches"][0]["line"], 1)

    def test_remote_patch_is_checked_and_deletion_is_explicit(self) -> None:
        if not shutil_which("git"):
            self.skipTest("git is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            target = root / "solver.py"
            target.write_text("old_value = 1\n", encoding="utf-8")
            previous = os.environ.get("KERR_QNM_WORKSPACE_ROOT")
            os.environ["KERR_QNM_WORKSPACE_ROOT"] = str(root)
            try:
                result = remote_workspace.apply_patch(
                    "--- a/solver.py\n+++ b/solver.py\n@@ -1 +1 @@\n-old_value = 1\n+new_value = 2\n"
                )
                changed_text = target.read_text(encoding="utf-8")
                with self.assertRaises(runtime.ToolkitError):
                    remote_workspace.apply_patch(
                        "--- a/solver.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-new_value = 2\n"
                    )
            finally:
                if previous is None:
                    os.environ.pop("KERR_QNM_WORKSPACE_ROOT", None)
                else:
                    os.environ["KERR_QNM_WORKSPACE_ROOT"] = previous
        self.assertTrue(result["applied"], result)
        self.assertEqual(changed_text, "new_value = 2\n")

    def test_python_file_and_jsonl_worker_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "script.py"
            script.write_text("import sys; print('|'.join(sys.argv[1:]))\n", encoding="utf-8")
            run = runtime.run_python_file(
                workspace_root=str(root),
                script_relative="script.py",
                arguments=["a", "b"],
                python_selection="compatible",
            )
            worker = root / "worker.py"
            worker.write_text((PLUGIN_ROOT / "fixtures" / "jsonl_echo_worker.py").read_text(encoding="utf-8"), encoding="utf-8")
            probe = runtime.jsonl_probe(
                workspace_root=str(root),
                language="python",
                script_relative="worker.py",
                messages=[{"spin": 0.7}, [2, 2, 0]],
                python_selection="compatible",
            )
        self.assertTrue(run["ok"], run)
        self.assertEqual(run["stdout"].strip(), "a|b")
        self.assertTrue(probe["ok"], probe)
        self.assertEqual(probe["responses"][0]["received"], {"spin": 0.7})

    def test_python_unittest_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_ok.py").write_text(
                "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self): self.assertEqual(2 + 2, 4)\n",
                encoding="utf-8",
            )
            result = runtime.python_tests(
                workspace_root=str(root),
                target_relative="tests",
                framework="unittest",
                python_selection="compatible",
            )
        self.assertTrue(result["ok"], result)

    def test_git_inspection_scrubs_remote(self) -> None:
        if not shutil_which("git"):
            self.skipTest("git is unavailable")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "remote", "add", "origin", "https://user:secret@example.com/owner/repo.git?token=x"],
                check=True,
            )
            report = runtime.git_inspect(str(root))
        self.assertTrue(report["is_repository"])
        self.assertEqual(report["remotes"]["origin"], ["https://example.com/owner/repo.git"])

    def test_mcp_initialize_and_tool_listing(self) -> None:
        requests = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            ]
        ) + "\n"
        completed = subprocess.run(
            [sys.executable, str(PLUGIN_ROOT / "toolkit_runtime" / "server.py")],
            input=requests,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=PLUGIN_ROOT,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        replies = [json.loads(line) for line in completed.stdout.splitlines()]
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "kerr-qnm-toolkit")
        names = {tool["name"] for tool in replies[1]["result"]["tools"]}
        self.assertEqual(
            names,
            {
                "kerr_qnm_toolchain_status",
                "kerr_qnm_prepare_toolchain",
                "kerr_qnm_inspect_workspace",
                "kerr_qnm_git_inspect",
                "kerr_qnm_run_julia_file",
                "kerr_qnm_run_python_file",
                "kerr_qnm_julia_project",
                "kerr_qnm_python_tests",
                "kerr_qnm_jsonl_probe",
                "kerr_qnm_numerical_canary",
            },
        )

    def test_managed_cross_language_canaries_when_provisioned(self) -> None:
        status = runtime.toolchain_status()
        if not status["ok"]:
            self.skipTest("managed toolchain is not provisioned")
        result = runtime.numerical_canary(mode="all")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["python"]["contract"]["numpy_version"], runtime.NUMPY_VERSION)
        self.assertEqual(result["python"]["contract"]["scipy_version"], runtime.SCIPY_VERSION)
        self.assertTrue(result["cross_language"]["contract"]["input_sha256"])

    def test_julia_project_status_and_tests_when_provisioned(self) -> None:
        status = runtime.toolchain_status()
        if not status["ok"]:
            self.skipTest("managed toolchain is not provisioned")
        root = PLUGIN_ROOT / "tests" / "fixtures"
        status_result = runtime.julia_project_action(
            workspace_root=str(root),
            project_relative="julia_project",
            action="status",
            julia_selection="pinned",
            use_managed_depot=True,
            timeout_seconds=120,
        )
        test_result = runtime.julia_project_action(
            workspace_root=str(root),
            project_relative="julia_project",
            action="test",
            julia_selection="pinned",
            use_managed_depot=True,
            timeout_seconds=120,
        )
        self.assertTrue(status_result["ok"], status_result)
        self.assertTrue(test_result["ok"], test_result)


def shutil_which(name: str) -> str | None:
    return shutil.which(name)


if __name__ == "__main__":
    unittest.main()
