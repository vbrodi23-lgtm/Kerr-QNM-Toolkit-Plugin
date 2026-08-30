# Remote workspace workflow

The service operates on one configured persistent workspace. Treat paths returned by tools as workspace-relative and never ask tools to reach outside that boundary.

## Source changes

Inspect Git state before editing. Read the whole relevant function or module, not only a search match. Form a minimal unified diff with repository-relative paths, apply it, inspect the resulting Git diff, and run the narrowest relevant checks before broader tests. Do not delete files unless the user intended that change.

The workspace persists across container restarts only when the deployment mounts durable storage at `/workspace`. A repository may be cloned into an empty volume at first start. The service never automatically pulls, rebases, commits, or pushes, so it cannot silently replace work or publish changes.

## Execution

Run existing files rather than passing source code through arguments. Prefer offline package operation. Enable Julia package network access only when dependency resolution is necessary and the user accepts that external state may change.

Treat timeout as a safety bound, not a performance target. For long computations, define the parameter range, checkpoint/output path, storage budget, and recovery plan before execution.

## Evidence

Tool output is diagnostic evidence from the current container and checkout. Record the Git commit and dirty state with runtime versions when retaining numerical findings. A clean canary validates the environment; it does not validate the user's physical model or solver implementation.
