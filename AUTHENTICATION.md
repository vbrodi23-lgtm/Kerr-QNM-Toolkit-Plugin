# Authentication boundary

This service can read, modify, and execute code in a persistent solver workspace. Do not expose `/mcp` anonymously on the public internet.

## Private deployment and smoke testing

Set `KERR_QNM_MCP_BEARER_TOKEN` to a long random secret. The built-in gate then requires `Authorization: Bearer <token>` for `/mcp`; `/healthz` remains public. This is useful for private MCP clients and deployment checks.

## ChatGPT web and mobile

The container includes a single-owner OAuth 2.1 authorization server for a private ChatGPT connection. It publishes protected-resource and authorization-server metadata, accepts only OpenAI's stable ChatGPT Client ID Metadata Document, uses the stable ChatGPT redirect URI, enforces the authorization-code flow with S256 PKCE, binds tokens to the exact `/mcp` resource, rotates refresh tokens, and validates every access token before executing a tool.

Set `KERR_QNM_PUBLIC_BASE_URL`, `KERR_QNM_OAUTH_PASSWORD`, and `KERR_QNM_OAUTH_SIGNING_SECRET` in the hosting platform's secret manager. The password and signing secret must be independent random values of at least 32 bytes and must never be committed. Configure the public HTTPS URL ending in `/mcp` when creating the private ChatGPT plugin connection. The owner enters `KERR_QNM_OAUTH_PASSWORD` only in the toolkit's HTTPS authorization page opened by ChatGPT.

This built-in authorization server is deliberately limited to the stable ChatGPT client and one owner. A different identity provider or multi-user product should replace it rather than weakening its client, redirect, audience, or scope checks.

Before public submission, replace this personal single-workspace topology with per-user isolated workspaces and access controls, or keep the plugin private. A public directory listing that maps every user to one writable solver checkout would be unsafe.
