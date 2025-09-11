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

Alternatively, you can use the following button:
[![Add Obsidian MCP to VS Code](https://img.shields.io/badge/Add_Obsidian_MCP-VS_Code-purple?logo=visualstudiocode)](vscode://obsidian.mcp/addServer?config=eyJpZCI6Im1jcC1vYnNpZGlhbiIsIm5hbWUiOiJPYnNpZGlhbiBNQ1AgU2VydmVyIiwiY29tbWFuZCI6InV2eCIsImFyZ3MiOlsibWNwLW9ic2lkaWFuIl0sImVudiI6eyJPQlNJRElBTl9BUElfS0VZIjoiWU9VUl9BUElfS0VZX0dPRVNfSEVSRSIsIk9CU0lESUFOX0hPU1QiOiIxMjcuMC4wLjEiLCJPQlNJRElBTl9QT1JUIjoiMjcxMjQifSwidHlwZSI6InN0ZGlvIn0=)

Note:
- You can find the API key in the Obsidian plugin config
- Default port is 27124 if not specified
- Default host is 127.0.0.1 if not specified

### (Recommended) Folder Path Instead of Manual ENV

Instead of setting any environment variables you can now simply supply a path
to your vault (or directly to the plugin config directory / its `data.json`).
The server will parse the Obsidian Local REST API plugin configuration and
populate the API key, enabled protocol and corresponding port automatically.
Note that the server plugin for Obsidian is still required.

Minimal examples (no env needed):

```
mcp-obsidian /path/to/MyVault
mcp-obsidian /path/to/MyVault --show-config
```

Claude Desktop config using just a folder path:

```jsonc
{
  "mcpServers": {
    "mcp-obsidian": {
      "command": "uvx",
      "args": [
        "mcp-obsidian",
        "/absolute/path/to/MyVault"
      ]
    }
  }
}
```

If both HTTP and HTTPS are enabled in the plugin and you want HTTP:

```
mcp-obsidian /path/to/MyVault --protocol http
```

Accepted path forms (all equivalent):

```
/path/to/MyVault
/path/to/MyVault/.obsidian
/path/to/MyVault/.obsidian/plugins
/path/to/MyVault/.obsidian/plugins/obsidian-local-rest-api
/path/to/MyVault/.obsidian/plugins/obsidian-local-rest-api/data.json
```

Precedence with folder path: existing `.env` / process env values are loaded
first, CLI overrides next, then the plugin configuration (for API key and
enabled protocol/ports). If the plugin enables only one protocol it will
override any conflicting choice.

## Quickstart

### Install

#### Obsidian REST API

You need the Obsidian REST API community plugin running: https://github.com/coddingtonbear/obsidian-local-rest-api

Install and enable it in the settings and copy the api key.

### Start by Vault Path (Auto Configuration)

You can now launch the server by simply pointing at your vault (or directly to the plugin config directory / data.json). The server will read the Local REST API plugin configuration and auto-set API key, ports and protocol.

Examples:

```
mcp-obsidian /path/to/MyVault
mcp-obsidian /path/to/MyVault/.obsidian
mcp-obsidian /path/to/MyVault/.obsidian/plugins
mcp-obsidian /path/to/MyVault/.obsidian/plugins/obsidian-local-rest-api
mcp-obsidian /path/to/MyVault/.obsidian/plugins/obsidian-local-rest-api/data.json
```

Force protocol when the plugin enables both:

```
mcp-obsidian /path/to/MyVault --protocol http
```

Show the resolved configuration without starting the server:

```
mcp-obsidian /path/to/MyVault --show-config
```

Precedence order (highest last): `.env / env` -> CLI options -> plugin configuration (api key & enabled ports). If the plugin only enables one protocol it will override any CLI or env choice.

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
