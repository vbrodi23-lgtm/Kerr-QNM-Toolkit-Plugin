# Remote deployment

The deployed shape is:

`ChatGPT web/mobile -> HTTPS + OAuth 2.1 -> /mcp -> Linux container -> persistent /workspace`

The image contains the verified bundled Julia 1.10.11 and CPython 3.12.13 profile, NumPy 2.4.6, SciPy 1.18.0, and the seeded Julia package depot. Runtime operation does not depend on the user's PC.

## 1. Put the source where a container host can build it

GitHub is optional, but it is the most common deployment source. The two large runtime archives exceed GitHub's normal per-file limit, so this repository marks `runtime-seed/*.tar.gz` for Git LFS. Install Git LFS before the first commit, or store the archives in a private release/object store and adapt the Docker build to download them with the hashes in `runtime-seed/toolchain-policy.json` verified.

## 2. Give the container persistent storage

Mount a durable volume at `/workspace`. If `KERR_QNM_SOLVER_REPOSITORY` names a public HTTPS or SSH repository, the container clones it only when that volume is empty. It never automatically pulls over local work. For a private repository, use the hosting platform's Git credential or SSH-key secret support; do not put credentials in the repository URL.

Use one replica for this personal workspace. Multiple replicas must not share a writable checkout without a coordination design.

## 3. Configure the public edge

- Terminate TLS at a stable HTTPS hostname.
- Forward the original `Host` and set that hostname in `KERR_QNM_ALLOWED_HOSTS`.
- Configure the built-in single-owner OAuth 2.1 service, or place the container behind a compatible external OAuth 2.1 authorization service; see `AUTHENTICATION.md`.
- Point the public MCP URL to `https://your-host.example/mcp`.
- Keep `/healthz` available to the hosting platform.

## 4. Verify before connecting ChatGPT

Build the image, start one container, call `/healthz`, connect with an MCP inspector using the private bearer token, list all tools, and run `kerr_qnm_numerical_canary`. Then inspect the solver workspace and run its existing Julia and Python tests.

## 5. Connect and submit

Create the plugin in ChatGPT's plugin developer interface using the production MCP URL and its discovered OAuth configuration. Upload the `skills/kerr-qnm-toolkit` skill bundle. Test the positive and negative prompts in `submission/PLUGIN_SUBMISSION.md`. Once connected to the account, the hosted service—not this PC—does the computation.

Public directory submission additionally requires verified developer identity, a verified domain, privacy/terms/support URLs, production branding, and review approval. A private account-scoped deployment does not become public merely because its MCP endpoint is hosted.
