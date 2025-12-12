# MCP server for Obsidian

MCP server to interact with Obsidian via the Local REST API community plugin.

<a href="https://glama.ai/mcp/servers/3wko1bhuek"><img width="380" height="200" src="https://glama.ai/mcp/servers/3wko1bhuek/badge" alt="server for Obsidian MCP server" /></a>

## Components

### Tools

The server implements multiple tools to interact with Obsidian:

- list_files_in_vault: Lists all files and directories in the root directory of your Obsidian vault
- list_files_in_dir: Lists all files and directories in a specific Obsidian directory
- get_file_contents: Return the content of a single file in your vault.
- search: Search for documents matching a specified text query across all files in the vault
- patch_content: Insert content into an existing note relative to a heading, block reference, or frontmatter field.
- append_content: Append content to a new or existing file in the vault.
- delete_file: Delete a file or directory from your vault.
- journal_entry: (Optional) Create reflective journal entries with structured metadata for capturing decisions, learnings, and insights during agent workflows.

### Example prompts

Its good to first instruct Claude to use Obsidian. Then it will always call the tool.

The use prompts like this:
- Get the contents of the last architecture call note and summarize them
- Search for all files where Azure CosmosDb is mentioned and quickly explain to me the context in which it is mentioned
- Summarize the last meeting notes and put them into a new note 'summary meeting.md'. Add an introduction so that I can send it via email.

## Configuration

### Obsidian REST API Key

There are two ways to configure the environment with the Obsidian REST API Key. 

1. Add to server config (preferred)

```json
{
  "mcp-obsidian": {
    "command": "uvx",
    "args": [
      "mcp-obsidian"
    ],
    "env": {
      "OBSIDIAN_API_KEY": "<your_api_key_here>",
      "OBSIDIAN_HOST": "<your_obsidian_host>",
      "OBSIDIAN_PORT": "<your_obsidian_port>"
    }
  }
}
```
Sometimes Claude has issues detecting the location of uv / uvx. You can use `which uvx` to find and paste the full path in above config in such cases.

2. Create a `.env` file in the working directory with the following required variables:

```
OBSIDIAN_API_KEY=your_api_key_here
OBSIDIAN_HOST=your_obsidian_host
OBSIDIAN_PORT=your_obsidian_port
```

Note:
- You can find the API key in the Obsidian plugin config
- Default port is 27124 if not specified
- Default host is 127.0.0.1 if not specified
- **IMPORTANT**: When using file paths (like `--env-file` or `OBSIDIAN_SSL_CERT_PATH`), always use full absolute paths like `/Users/username/...` instead of `~/...` - tilde expansion may not work correctly in all contexts

### Optional: Custom SSL Certificate

By default, SSL certificate verification is disabled (`verify=False`). To use a custom SSL certificate for the Obsidian REST API connection without adding it to your system keychain, you have two options:

**Option 1: Base64-encoded certificate (recommended)**

Download the certificate from your Obsidian Local REST API plugin, encode it as base64, and provide it via environment variable:

```bash
# Encode your certificate
base64 -i /path/to/cert.pem | tr -d '\n' > cert.base64

# Add to your MCP configuration
{
  "env": {
    "OBSIDIAN_API_KEY": "<your_api_key_here>",
    "OBSIDIAN_HOST": "<your_obsidian_host>",
    "OBSIDIAN_PORT": "<your_obsidian_port>",
    "OBSIDIAN_SSL_CERT_BASE64": "<contents_of_cert.base64>"
  }
}
```

**Option 2: Path to certificate file**

Alternatively, provide the path to your certificate file:

```json
{
  "env": {
    "OBSIDIAN_API_KEY": "<your_api_key_here>",
    "OBSIDIAN_HOST": "<your_obsidian_host>",
    "OBSIDIAN_PORT": "<your_obsidian_port>",
    "OBSIDIAN_SSL_CERT_PATH": "/path/to/cert.pem"
  }
}
```

**Why use this?** Avoids having to add the certificate to your system keychain and mark it as globally trusted. The certificate is only used for this specific connection.

**Certificate source:** Download the certificate from the Obsidian Local REST API plugin settings (usually available at `https://127.0.0.1:27124/` in your browser - look for the certificate download or export option).

### Optional: Journaling Feature

The journaling tool automates the mechanical parts of logging (timestamps, formatting, file organization) so LLMs can focus on content. Gated behind a feature flag because it requires thoughtful prompting to be valuable.

**To enable:** Add `OBSIDIAN_ENABLE_JOURNALING=true` to your environment variables.

**Why use this?** Helps with rubber duck debugging, cross-session continuity, and post-project synthesis. See [JOURNALING.md](JOURNALING.md) for detailed guidance on getting value from agent journaling.

### Optional: Disable Simple Search

For large vaults (many files or large files), the simple search can return excessive context that overwhelms token limits. Use this to disable simple search and rely on complex search instead.

**To disable:** Add `OBSIDIAN_DISABLE_SIMPLE_SEARCH=true` to your environment variables.

**Example configuration:**
```json
{
  "env": {
    "OBSIDIAN_API_KEY": "<your_api_key_here>",
    "OBSIDIAN_HOST": "<your_obsidian_host>",
    "OBSIDIAN_PORT": "<your_obsidian_port>",
    "OBSIDIAN_DISABLE_SIMPLE_SEARCH": "true"
  }
}
```

### Optional: Debug Logging

Enable detailed debug logging to troubleshoot connection issues, SSL certificate problems, or API errors. Debug logs include:
- Environment configuration and SSL cert setup
- MCP tool calls (requests and responses)
- API requests and detailed error messages
- Full stack traces for errors

**To enable:** Add `OBSIDIAN_DEBUG_LOG=/path/to/debug.log` to your environment variables.

**Example configuration:**
```json
{
  "env": {
    "OBSIDIAN_API_KEY": "<your_api_key_here>",
    "OBSIDIAN_HOST": "<your_obsidian_host>",
    "OBSIDIAN_PORT": "<your_obsidian_port>",
    "OBSIDIAN_DEBUG_LOG": "/tmp/mcp-obsidian-debug.log"
  }
}
```

**Why use this?** MCP servers use stdio for communication, making it difficult to debug connection or SSL issues. This feature logs all diagnostic information to a separate file without interfering with the MCP protocol.

**Tip:** Use `tail -f /tmp/mcp-obsidian-debug.log` in a separate terminal to watch logs in real-time.

## Quickstart

### Install

#### Obsidian REST API

You need the Obsidian REST API community plugin running: https://github.com/coddingtonbear/obsidian-local-rest-api

Install and enable it in the settings and copy the api key.

#### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`

On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  
```json
{
  "mcpServers": {
    "mcp-obsidian": {
      "command": "uv",
      "args": [
        "--directory",
        "<dir_to>/mcp-obsidian",
        "run",
        "mcp-obsidian"
      ],
      "env": {
        "OBSIDIAN_API_KEY": "<your_api_key_here>",
        "OBSIDIAN_HOST": "<your_obsidian_host>",
        "OBSIDIAN_PORT": "<your_obsidian_port>"
      }
    }
  }
}
```
</details>

<details>
  <summary>Published Servers Configuration</summary>
  
```json
{
  "mcpServers": {
    "mcp-obsidian": {
      "command": "uvx",
      "args": [
        "mcp-obsidian"
      ],
      "env": {
        "OBSIDIAN_API_KEY": "<YOUR_OBSIDIAN_API_KEY>",
        "OBSIDIAN_HOST": "<your_obsidian_host>",
        "OBSIDIAN_PORT": "<your_obsidian_port>"
      }
    }
  }
}
```
</details>

## Development

### Building

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).

You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /path/to/mcp-obsidian run mcp-obsidian
```

Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.

You can also watch the server logs with this command:

```bash
tail -n 20 -f ~/Library/Logs/Claude/mcp-server-mcp-obsidian.log
```
