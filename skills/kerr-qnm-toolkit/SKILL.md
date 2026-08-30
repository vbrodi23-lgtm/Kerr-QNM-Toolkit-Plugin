---
name: kerr-qnm-toolkit
description: Develop, inspect, run, test, or audit Julia and Python software for Kerr black-hole perturbations and quasinormal modes directly in a Codex Cloud Git checkout. Use for Julia, NumPy/SciPy, source review and patches, project and package workflows, cross-language workers, numerical canaries, reproducibility, and Git-aware solver work.
---

# Kerr QNM Toolkit

Work directly in the user's current Git checkout. Keep that repository's scientific objective, equations, conventions, precision model, and acceptance criteria authoritative. This plugin supplies a bounded local command bridge and research workflow, not a universal perturbation formalism.

The plugin root is two directories above this `SKILL.md`; its command bridge is `scripts/kerr_qnm_toolkit.py` beneath that root. Resolve the script to an absolute path before invoking it. Pass the target solver checkout as an absolute `--workspace-root`. Never assume the plugin source and target solver repository are the same checkout.

## Route the work

- Start unfamiliar work with `inspect-workspace` and `git-inspect` against the checkout root.
- Use Codex's native repository tools first for ordinary file reading, searching, and edits. The bridge also exposes bounded `list-files`, `read-text`, `search-text`, `git-diff`, and `apply-patch` commands for scripted workflows.
- Run `toolchain-status` before relying on exact versions. If the bundled assets are available but the managed runtime is not, run `prepare-toolchain` once. Prefer a compatible project/system runtime when the repository deliberately supports another version.
- Run existing Julia or Python files with `run-julia` or `run-python`. Use `julia-project` for package status, instantiation, precompilation, resolution, and tests; use `python-tests` for pytest or unittest.
- Use `jsonl-probe` for line-framed Julia/Python worker protocols. Use `numerical-canary` to check Julia, NumPy/SciPy, and cross-language transfer contracts.
- Before changing source, read the relevant code and current Git diff. Apply a minimal patch, inspect the resulting diff, and run proportionate tests. Permit deletion only when the user intended it.
- For GitHub pull requests, issues, workflows, or CI, use an available GitHub integration after inspecting the checkout. Do not infer current GitHub state from local Git metadata alone.

Short tests, canaries, and focused debugging runs are allowed. Obtain direct user instruction before a long parameter sweep, resumed production computation, expensive broad search, or result intended as scientific evidence.

For local commands, workspace containment, and source-change boundaries, read [cloud-workspace.md](references/cloud-workspace.md). For conventions, numerical review, and reproducibility, read [research-workflows.md](references/research-workflows.md).
