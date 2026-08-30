# Authentication boundary

This service can read, modify, and execute code in a persistent solver workspace. Do not expose `/mcp` anonymously on the public internet.

## Private deployment and smoke testing

Set `KERR_QNM_MCP_BEARER_TOKEN` to a long random secret. The built-in gate then requires `Authorization: Bearer <token>` for `/mcp`; `/healthz` remains public. This is useful for private MCP clients and deployment checks.

## ChatGPT web and mobile

Put the service behind an OAuth 2.1 authorization gateway that implements the MCP authorization profile, including protected-resource metadata, PKCE, and the authorization-code flow. The gateway must authenticate only the intended user, inject the fixed upstream bearer token, and never expose that token to the client. Configure the public HTTPS URL ending in `/mcp` when creating the ChatGPT plugin.

The repository intentionally does not invent a user identity system. Suitable production choices include an identity-aware gateway or a small authorization service connected to the user's existing identity provider. The exact callback URLs and client registration method should be taken from the ChatGPT plugin setup screen for the target account or organization.

Before public submission, replace this personal single-workspace topology with per-user isolated workspaces and access controls, or keep the plugin private. A public directory listing that maps every user to one writable solver checkout would be unsafe.
