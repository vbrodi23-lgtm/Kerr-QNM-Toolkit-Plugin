---
name: kerr-qnm-toolkit
description: Develop, inspect, test, or audit Julia and Python software for Kerr black-hole perturbations and quasinormal modes in a persistent remote Linux workspace. Use for source review and patches, NumPy/SciPy or Julia execution, cross-language workers, numerical checks, reproducibility, and Git-aware solver work.
---

# Kerr QNM Toolkit

Use the toolkit's MCP tools for the configured remote solver workspace. Keep the scientific objective and conventions from the user's repository authoritative; the toolkit supplies a computational environment and development operations, not a universal perturbation formalism.

## Route the work

- Start unfamiliar work with `kerr_qnm_inspect_workspace` and `kerr_qnm_git_inspect`.
- Use `kerr_qnm_list_files`, `kerr_qnm_search_text`, and `kerr_qnm_read_text_file` to ground reasoning in the actual solver source.
- Use `kerr_qnm_toolchain_status` before relying on exact versions. The container image already provisions the pinned Julia/Python profile.
- Run existing Julia or Python entry points with the corresponding file tool. Use `kerr_qnm_julia_project` for package status, instantiation, precompilation, resolution, and tests; use `kerr_qnm_python_tests` for pytest or unittest.
- Use `kerr_qnm_jsonl_probe` for line-framed Julia/Python worker protocols. Use `kerr_qnm_numerical_canary` to check the managed numerical stack and cross-language file transfer.
- Before changing source, read the relevant files and current Git diff. Apply a minimal unified diff with `kerr_qnm_apply_patch`, then inspect the resulting diff and run proportionate tests. Set `allow_deletes=true` only when the user intends file deletion.
- For remote GitHub pull requests, issues, workflows, or CI, use an available GitHub integration after inspecting this workspace. Do not infer remote state from local Git metadata alone.

Short tests, canaries, and focused debugging runs are allowed. Obtain direct user instruction before a long parameter sweep, resumed production computation, expensive broad search, or result intended as scientific evidence.

For container workflow and source-change boundaries, read [remote-workspace.md](references/remote-workspace.md). For conventions, numerical review, and reproducibility, read [research-workflows.md](references/research-workflows.md).
