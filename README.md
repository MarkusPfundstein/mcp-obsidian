# documentation-mcp

`documentation-mcp` is a client-independent, read-only Model Context Protocol
server for compact Markdown retrieval through the Obsidian Local REST API.

It is derived from
[`MarkusPfundstein/mcp-obsidian`](https://github.com/MarkusPfundstein/mcp-obsidian)
and preserves the upstream MIT License.

## MCP compatibility

The server uses the standard local MCP `stdio` transport. Any MCP client that
can launch a command with arguments and environment variables can use it. The
runtime contains no OpenCode-, model-, or agent-specific code.

Every compatible client launches the same command:

```zsh
uvx \
  --from 'git+https://github.com/julZanozina/documentation-mcp.git@371cf299243e575144f546afd7c86f766a3352bf' \
  documentation-mcp \
  --config '/path/to/config.toml'
```

The alpha currently uses an immutable commit because `v0.1.0a1` has not been
published. Replace the commit only with a newer reviewed commit or a verified
release tag; do not use a mutable branch name.

The following marked command is the exact installation smoke test executed by
CI. It verifies that the immutable source exists and provides the expected
entry point without requiring an Obsidian configuration:

<!-- documentation-mcp-install-smoke-test:start -->
```zsh
uvx --refresh \
  --from 'git+https://github.com/julZanozina/documentation-mcp.git@371cf299243e575144f546afd7c86f766a3352bf' \
  documentation-mcp --help
```
<!-- documentation-mcp-install-smoke-test:end -->

The temporary Git source command pins the server code, but it does not consume
`uv.lock`; dependency versions may therefore change as compatible releases are
published. Use the locked release-artifact procedure below when reproducible
dependency versions are required.

Clients that support only remote HTTP MCP require a separate gateway, which is
outside this alpha.

## Security model

- Only HTTPS loopback Obsidian endpoints are accepted.
- TLS verification requires an explicit CA certificate.
- Every path is checked against configured documentation roots.
- Absolute paths, traversal, encoded traversal, and backslashes are rejected.
- No write, delete, unrestricted full-file, or batch-read tools exist.
- The API key is read only from `DOCUMENTATION_MCP_OBSIDIAN_API_KEY`.

See [SECURITY.md](SECURITY.md) for operational guidance.

## Tools

| Tool | Purpose |
| --- | --- |
| `scope_info` | Report enforced scope, limits, index snapshot, and access. |
| `refresh_index` | Read the source and atomically replace the index after a successful bounded rebuild. |
| `search_docs` | Return ranked, bounded Markdown sections. |
| `get_document_metadata` | Return allowlisted metadata fields without the full body. |
| `get_document_section` | Return one bounded section by stable identity. |
| `get_related_documents` | Return directly related document metadata. |

## Requirements

- Python 3.11 or later
- [`uv`](https://docs.astral.sh/uv/)
- Obsidian with
  [`obsidian-local-rest-api`](https://github.com/coddingtonbear/obsidian-local-rest-api)
- The Local REST API certificate exported to a local file

## Server configuration

### Get started

1. Export the Obsidian Local REST API certificate to a local file.
2. Create a private `config.toml` with the minimum required settings:

   ```toml
   allowed_directories = ["Documentation"]

   [obsidian]
   base_url = "https://127.0.0.1:27124"
   ca_certificate = "/path/to/obsidian-local-rest-api.crt"
   ```

3. Supply the API key to the MCP client process:

   ```zsh
   export DOCUMENTATION_MCP_OBSIDIAN_API_KEY='your-local-api-key'
   ```

4. Configure the client with the command and environment values shown in
   [Generic client values](#generic-client-values).

Keep `config.toml`, the certificate, and the API key private. Do not commit
them. See `config.example.toml` for a complete example with explicit limits
and filters.

### Settings reference

| Setting | Required | Default | Purpose |
| --- | --- | --- | --- |
| `allowed_directories` | Yes | — | Non-empty list of vault directories that the server may index. |
| `obsidian.base_url` | Yes | — | HTTPS loopback URL for the Obsidian Local REST API. |
| `obsidian.ca_certificate` | Yes | — | Path to the certificate used to verify the local HTTPS endpoint. |
| `DOCUMENTATION_MCP_OBSIDIAN_API_KEY` | Yes | — | API key supplied through the process environment, never TOML. |
| `backend` | No | `"obsidian"` | Backend selection; this release supports only `obsidian`. |
| `allowed_statuses` | No | `[]` | Frontmatter statuses to include; an empty list allows every status. |
| `allowed_types` | No | `[]` | Frontmatter types to include; an empty list allows every type. |
| `excluded_directories` | No | `[]` | Path components or scoped subtrees that must not be indexed. |
| `limits.top_k` | No | `5` | Maximum number of ranked results. |
| `limits.max_total_characters` | No | `12000` | Maximum serialized JSON character budget for a search response. |
| `limits.max_sections` | No | `4` | Maximum number of sections in one search response. |
| `limits.max_documents` | No | `2` | Maximum number of distinct documents in one search response. |
| `limits.max_sections_per_document` | No | `2` | Maximum sections returned from one document. |
| `limits.related_document_hops` | No | `1` | Related-document traversal depth; accepted values are `0` and `1`. |
| `limits.max_file_bytes` | No | `1048576` | Maximum downloaded and parsed size of one Markdown file. |
| `limits.max_total_index_bytes` | No | `33554432` | Maximum source bytes processed during one index build. |
| `limits.max_source_files` | No | `2000` | Maximum Markdown paths discovered during one index build. |
| `limits.max_source_directories` | No | `500` | Maximum unique vault directories discovered or queued during one index build. |
| `limits.max_directory_entries` | No | `5000` | Maximum entries accepted from one directory listing. |
| `limits.max_directory_response_bytes` | No | `1048576` | Maximum downloaded size of one directory response. |
| `limits.max_index_documents` | No | `1000` | Maximum complete documents retained in the index. |
| `limits.max_index_sections` | No | `10000` | Maximum complete sections retained across the index. |
| `limits.max_index_sections_per_document` | No | `200` | Maximum sections parsed from one document. |
| `limits.max_tokens_per_section` | No | `10000` | Maximum searchable tokens accepted in one section. |
| `limits.max_total_index_tokens` | No | `500000` | Maximum searchable tokens retained across the index. |
| `limits.max_frontmatter_bytes` | No | `65536` | Maximum UTF-8 size of one YAML frontmatter block. |
| `limits.max_frontmatter_nodes` | No | `1000` | Maximum scalar and collection nodes in frontmatter. |
| `limits.max_frontmatter_depth` | No | `20` | Maximum collection nesting depth in frontmatter. |
| `limits.max_index_build_seconds` | No | `120.0` | Maximum wall-clock duration of one index build; an incomplete refresh does not replace the active index. |
| `obsidian.connect_timeout_seconds` | No | `3.0` | Connection timeout for Obsidian requests. |
| `obsidian.read_timeout_seconds` | No | `10.0` | Read timeout for Obsidian requests. |
| `obsidian.request_retry_attempts` | No | `3` | Total attempts for transient Obsidian request failures; accepted values are `1` through `5`. |
| `obsidian.retry_backoff_seconds` | No | `0.25` | Positive initial exponential retry delay, capped at five seconds and by the index-build deadline. |

All numeric limits and timeouts must be positive, except
`related_document_hops`, which may be `0` or `1`.
YAML aliases are rejected. A document that exceeds any per-document parsing
limit is skipped as a whole; partial content is never retained. The bounded
diagnostics in `scope_info` identify skipped sources and reason codes.

`refresh_index` is read-only: it builds a separate candidate index and swaps
it into service only after the complete bounded build succeeds. A failed
or traversal-limited refresh preserves the last-known-good snapshot. On
startup, the stdio transport begins before the initial candidate build starts
in a worker. Until its atomic swap completes, the active index is empty and
`scope_info.refresh.status` is `running`; clients that require indexed content
can poll this read-only status. Retrieval tools fail with an explicit,
retriable `documentation index is not ready` error until the first successful
index is available; they never turn an incomplete or failed initial build into
an authoritative empty result. Candidate construction runs outside the MCP
event loop, so retrieval tools continue to use the active snapshot during
later refreshes. Each `scope_info` response reports one atomic index-and-refresh
generation.
`scope_info.refresh` reports the latest attempt time, duration, status, whether
the previous snapshot was preserved, skipped-document count, and bounded
indexing errors. Transient timeouts, connection failures, HTTP 408/425/429
responses, and HTTP 5xx responses use the configured bounded backoff policy.

### Expanded example

```toml
backend = "obsidian"

allowed_directories = ["Documentation"]
allowed_statuses = ["active", "unreviewed"]
allowed_types = []
excluded_directories = ["_inventory", "_meta", "_migration"]

[limits]
top_k = 5
max_total_characters = 12000
max_sections = 4
max_documents = 2
max_sections_per_document = 2
related_document_hops = 1
max_file_bytes = 1048576
max_total_index_bytes = 33554432
max_source_files = 2000
max_source_directories = 500
max_directory_entries = 5000
max_directory_response_bytes = 1048576
max_index_documents = 1000
max_index_sections = 10000
max_index_sections_per_document = 200
max_tokens_per_section = 10000
max_total_index_tokens = 500000
max_frontmatter_bytes = 65536
max_frontmatter_nodes = 1000
max_frontmatter_depth = 20
max_index_build_seconds = 120.0

[obsidian]
base_url = "https://127.0.0.1:27124"
ca_certificate = "/path/to/obsidian-local-rest-api.crt"
connect_timeout_seconds = 3.0
read_timeout_seconds = 10.0
request_retry_attempts = 3
retry_backoff_seconds = 0.25
```

A bare exclusion such as `_meta` matches that complete path component
anywhere under an allowed root. A scoped exclusion such as
`Documentation/private` matches only that exact vault path and its descendants.
Scoped exclusions outside every `allowed_directories` root are rejected during
startup.

`max_total_characters` caps the complete serialized JSON returned by
`search_docs`, including its response envelope, field names, punctuation, and
string escaping. If the remaining budget cannot fit a result's metadata and at
least one excerpt character, that result is omitted. A client limit too small
for the empty response envelope is rejected.

Search first selects the highest-scoring substantive direct section. It may
then select one meaningfully relevant complementary section through a
`related_documents` edge declared by that primary document. Structural roles
are inferred generically from headings, including interface/default,
configuration, behavior, validation, edge-case, integration, reference, and
test coverage. A routed section must retain at least 30% of the primary's
direct score. For a setting-, preference-, default-, or configuration-oriented
query, a relevant interface or default section with a Markdown setting/default
table is preferred over a peripheral interface representation. Relationship
links never increase scores. Only one hop is examined, reciprocal links are
not expanded again, inactive or filtered targets are ignored, and serialized
context is reserved for a selected complement before the primary excerpt is
filled. The configured section, document, per-document, hop, and complete JSON
response limits remain final.

`get_document_metadata` returns only `document_id`, `source`, `title`,
`summary`, `status`, `type`, `area`, `evidence`, `tags`,
`related_documents`, and `section_count`. Arbitrary frontmatter is never
returned. Values in these public fields are returned as stored, so do not put
credentials or other secrets in them. List-valued public fields accept string
items only.

Use the client’s secret or environment mechanism instead of placing the key in
a shared configuration file.

## Generic client values

MCP clients use different configuration file formats, but all receive:

```text
transport: stdio
command: uvx
arguments:
  --from
  git+https://github.com/julZanozina/documentation-mcp.git@371cf299243e575144f546afd7c86f766a3352bf
  documentation-mcp
  --config
  /path/to/config.toml
environment:
  DOCUMENTATION_MCP_OBSIDIAN_API_KEY: supplied securely by the client
```

### OpenCode example

OpenCode is one example; no server change is needed for another MCP client.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "documentation": {
      "type": "local",
      "command": [
        "uvx",
        "--from",
        "git+https://github.com/julZanozina/documentation-mcp.git@371cf299243e575144f546afd7c86f766a3352bf",
        "documentation-mcp",
        "--config",
        "/path/to/config.toml"
      ],
      "enabled": true,
      "environment": {
        "DOCUMENTATION_MCP_OBSIDIAN_API_KEY": "{env:DOCUMENTATION_MCP_OBSIDIAN_API_KEY}"
      },
      "timeout": 30000
    }
  }
}
```

## Metadata

Metadata is optional, but stable IDs and relationships improve routing:

```yaml
---
document_id: payments-retry
title: Payment retry behavior
summary: Retry handling after a provider timeout.
status: active
type: feature-doc
area: payments
evidence: specified
tags: [payments, retry]
related_documents: [payments-provider]
---
```

## Development

```zsh
uv sync --group dev
uv run pytest -q
uv run pyright
uv build --no-sources
```

Tests use synthetic documentation. Do not add private notes, credentials,
certificates, local configuration, or benchmark results.

## Dependency and release policy

- `uv.lock` is committed and CI installs it with `uv sync --locked`.
- CI extracts the locked runtime dependency set and checks it with
  `pip-audit`.
- Dependabot checks both Python/uv dependencies and pinned GitHub Actions
  weekly.
- Release tags must be annotated and exactly match `v<project.version>`.
- A valid tag runs the tests, type checker, dependency audit, package build,
  and tag-based installation smoke test before GitHub Release publication.
- Each GitHub Release contains the wheel, source distribution, hashed runtime
  requirements, and SHA-256 checksums.

For a reproducible released installation, download the wheel,
`runtime-requirements.txt`, and `SHA256SUMS` from the same GitHub Release into
one directory. Verify the release assets, then make both the released wheel and
its exact locked runtime dependency set part of the client command:

```zsh
shasum -a 256 -c SHA256SUMS

uvx --isolated \
  --with-requirements './runtime-requirements.txt' \
  --from './documentation_mcp-0.1.0a1-py3-none-any.whl' \
  documentation-mcp \
  --config '/path/to/config.toml'
```

Do not combine a wheel from one release with requirements or checksums from
another release.

Before `v0.1.0a1` is released, verify the temporary documented source with:

```zsh
uv run --frozen python scripts/verify_documented_install.py
```
