# Kerr QNM Toolkit

Kerr QNM Toolkit is a containerized remote MCP service for developing numerical software used in Kerr black-hole perturbation and quasinormal-mode research. ChatGPT can inspect, edit, run, test, and audit a persistent solver checkout while Julia and Python execute inside a Linux container rather than on the user's phone or PC.

## Capabilities

| Area | Operations |
| --- | --- |
| Source | List, read, and search bounded files; validate and apply Git patches; show diffs |
| Toolchain | Inspect a self-contained Linux Julia, CPython, NumPy, SciPy, and Julia package-cache profile |
| Workspaces | Discover Julia/Python projects, tests, notebooks, workflows, and common research file types |
| Julia | Run existing scripts; inspect, instantiate, precompile, resolve, or test a project |
| Python | Run existing scripts with the managed or a project interpreter; run pytest or unittest |
| Numerics | Exercise complex linear algebra, root finding, ODE integration, special functions, FFTs, and Julia/Python transfer contracts |
| Protocols | Feed JSON Lines messages to existing Julia or Python workers and validate response framing |
| Git | Report repository root, branch, commit, worktree state, submodules, credential-scrubbed remotes, and diffs |

The public interface accepts no shell command strings or inline source programs. File and execution tools are contained below the configured `/workspace`, use argument vectors, limit output, and enforce timeouts. Source changes use a checked unified Git patch.

## Reproducible Linux image

The image provisions verified bundled assets during its build:

- Julia 1.10.11
- CPython 3.12.13
- NumPy 2.4.6
- SciPy 1.18.0
- a Julia scientific depot seed containing cached numerical packages

The container is intentionally a computational service, not a universal Kerr perturbation formalism. The solver repository remains authoritative for equations, units, conventions, branches, precision, and acceptance criteria.

## Start here

Read [DEPLOYMENT.md](DEPLOYMENT.md) for the hosting path and [AUTHENTICATION.md](AUTHENTICATION.md) before exposing the service. A local smoke test can use `docker compose up --build`; production ChatGPT access requires a stable HTTPS endpoint and OAuth 2.1 boundary.

The original stdio server remains available through `.mcp.json` for developer diagnostics. It is not the mobile/web deployment path.

## Development

Run the source checks with:

```bash
python3 -m unittest discover -s tests -v
```

The repository is MIT licensed. Contributions should keep public APIs project-neutral, preserve path containment and timeout checks, and add an observable test for each new execution mode.
