# Security policy

## Security model

`documentation-mcp` is intentionally read-only. It exposes no tool that can
create, edit, append, patch, replace, or delete vault content.

The server initializes only the MCP `stdio` transport. HTTP, SSE, and WebSocket
transports included transitively by the MCP SDK are not configured or exposed.

The Obsidian backend:

- accepts only HTTPS loopback endpoints;
- requires certificate verification with an explicit CA certificate;
- restricts every path to configured documentation roots;
- rejects scoped exclusions outside configured documentation roots;
- rejects absolute paths, traversal, encoded traversal, and backslashes;
- reads the API key only from `DOCUMENTATION_MCP_OBSIDIAN_API_KEY`.

Metadata responses contain only explicitly allowlisted fields. Raw frontmatter
and non-string items nested in list-valued metadata are not returned. Values
stored in allowlisted fields are still public to MCP clients and must not
contain credentials or other secrets.

Do not commit API keys, certificates, local `config.toml` files, logs, or
retrieval output.

## Reporting a vulnerability

Do not open a public issue containing a credential, exploit payload, private
document, or other sensitive information. Use GitHub's private vulnerability
reporting feature when it is enabled for this repository.
