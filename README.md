# Kerr QNM Toolkit

Kerr QNM Toolkit is a repo-backed Codex plugin for developing numerical software used in Kerr black-hole perturbation and quasinormal-mode research. It runs Julia, Python, NumPy, SciPy, tests, and interoperability probes directly in a Codex Cloud Linux checkout. It does not require an MCP server, container service, API token, or external compute host.

## Capabilities

| Area | Operations |
| --- | --- |
| Source | Discover, list, read, and search bounded files; validate and apply Git patches; show diffs |
| Toolchain | Inspect or provision a verified Linux Julia, CPython, NumPy, SciPy, and Julia package-cache profile |
| Workspaces | Discover Julia/Python projects, manifests, tests, notebooks, workflows, data, and research file types |
| Julia | Run existing scripts; inspect, instantiate, precompile, resolve, or test projects; control depot, threads, network, and runtime selection |
| Python | Run existing scripts with managed, project-local, system, or explicit Python; run pytest or unittest |
| Numerics | Exercise complex linear algebra, root finding, ODE integration, special functions, FFTs, and Julia/Python transfer contracts |
| Protocols | Feed JSON Lines messages to existing Julia or Python workers and validate response framing |
| Git | Report repository root, branch, commit, worktree state, submodules, credential-scrubbed remotes, and diffs |

The command bridge accepts no shell command strings or inline source programs. Selected files stay beneath an explicit checkout root, subprocesses use argument vectors, output is clipped, and every execution has a bounded timeout.

## Install from GitHub

Add this repository as a Codex marketplace and install the plugin:

```bash
codex plugin marketplace add vbrodi23-lgtm/Kerr-QNM-Toolkit-Plugin --ref main
codex plugin add kerr-qnm-toolkit@kerr-qnm-toolkit
```

Start a new Codex thread after installation so the skill is loaded. Connect the solver repository you want to work on to a Codex Cloud environment, then ask the plugin to inspect or test that checkout.

## Local command bridge

Codex calls the bundled bridge from the installed plugin and passes your solver repository as `--workspace-root`:

```bash
python3 scripts/kerr_qnm_toolkit.py inspect-workspace --workspace-root "$PWD"
python3 scripts/kerr_qnm_toolkit.py toolchain-status --verify-assets
python3 scripts/kerr_qnm_toolkit.py prepare-toolchain
python3 scripts/kerr_qnm_toolkit.py numerical-canary --mode all
```

Use `python3 scripts/kerr_qnm_toolkit.py --help` to see all commands and `<command> --help` for structured options. Normal source work can also use Codex's native file and Git tools; the bridge exists for bounded, reproducible operations and cross-language automation.

## Reproducible Linux profile

The repository includes verified bundled assets for:

- Julia 1.10.11;
- CPython 3.12.13;
- NumPy 2.4.6;
- SciPy 1.18.0;
- a Julia scientific depot seed containing cached numerical packages.

The profile targets Linux x86_64. Projects remain authoritative for their supported runtimes, manifests, equations, units, conventions, branches, precision, and acceptance criteria. The toolkit is intentionally broad computational infrastructure, not a hard-coded Kerr perturbation formulation.

## Safety and scientific scope

Short unit tests, focused debugging runs, JSONL probes, and deterministic numerical canaries are allowed. Long parameter sweeps, resumed production computations, expensive broad searches, or results intended as scientific evidence require an explicit objective and user authorization.

The canary validates the toolchain and data-transfer contract. It does not validate a physical model, boundary condition, mode convention, or solver result.

## Development

Run the checks with:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/kerr_qnm_toolkit.py inspect-workspace --workspace-root "$PWD"
```

The repository is MIT licensed. Contributions should keep public APIs project-neutral, preserve path containment and timeout checks, and add an observable test for each execution mode.
