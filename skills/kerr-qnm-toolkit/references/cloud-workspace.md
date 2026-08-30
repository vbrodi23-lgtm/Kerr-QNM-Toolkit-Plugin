# Codex Cloud workspace workflow

The plugin runs short-lived commands inside the Codex Cloud Linux environment. It does not connect to an MCP server or hosted compute service. Treat the current Git checkout as the workspace and pass its absolute path explicitly to every command that needs `--workspace-root`.

## Command bridge

Resolve `scripts/kerr_qnm_toolkit.py` from the installed plugin root, then inspect its current interface with `python3 <toolkit-cli> --help` or `python3 <toolkit-cli> <command> --help`. Output is structured JSON. A successful diagnostic may omit `ok`; commands that execute or provision software return an explicit `ok` value and a nonzero exit status on failure.

The command groups are:

- environment: `toolchain-status`, `prepare-toolchain`;
- repository: `inspect-workspace`, `git-inspect`, `list-files`, `read-text`, `search-text`, `git-diff`, `apply-patch`;
- execution: `run-julia`, `run-python`, `julia-project`, `python-tests`;
- interoperability: `jsonl-probe`, `numerical-canary`.

## Source changes

Inspect Git state before editing. Read the whole relevant function or module, not only a search match. Form a minimal unified diff with repository-relative paths, apply it, inspect the resulting Git diff, and run the narrowest relevant checks before broader tests. Do not delete files unless the user intended that change.

The command bridge never automatically clones, pulls, rebases, commits, pushes, or changes branches. Codex should use ordinary Git commands or a GitHub integration for those operations, within the user's authorization.

## Execution

Run existing files rather than passing source code through arguments. Prefer offline Julia package operation. Use `--allow-network` only when dependency resolution is necessary and the environment permits it.

The managed runtime defaults below the Cloud user's home directory and can be overridden with `--runtime-root`. It is Linux x86_64 only. `prepare-toolchain` verifies bundled hashes before extraction and provisions Julia, CPython, NumPy, SciPy, and the Julia depot seed without requiring a long-lived process.

Treat timeout as a safety bound, not a performance target. For long computations, define the parameter range, checkpoint/output path, storage budget, and recovery plan before execution.

## Evidence

Command output is diagnostic evidence from the current Cloud environment and checkout. Record the Git commit and dirty state with runtime versions when retaining numerical findings. A clean canary validates the environment; it does not validate the user's physical model or solver implementation.
