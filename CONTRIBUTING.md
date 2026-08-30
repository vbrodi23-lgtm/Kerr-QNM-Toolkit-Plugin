# Contributing

Contributions that improve Julia/Python interoperability, numerical reproducibility, Kerr perturbation workflows, Codex Cloud support, tests, or documentation are welcome.

Please keep tool inputs structured: use existing workspace files and argument lists rather than shell snippets or inline source strings. New subprocess operations need a bounded timeout, path-containment checks where files are selected, clipped output, and tests for both successful and rejected inputs.

Do not add `.mcp.json`, `mcpServers`, a socket listener, or hosted-service credentials. The plugin must remain usable as a GitHub-backed skill and local command bridge in a connected Codex Cloud checkout.

Before submitting a change, run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/kerr_qnm_toolkit.py inspect-workspace --workspace-root "$PWD"
python3 /path/to/plugin-creator/scripts/validate_plugin.py .
```
