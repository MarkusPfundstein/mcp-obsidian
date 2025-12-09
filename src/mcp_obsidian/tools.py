from collections.abc import Sequence
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
import json
import os
import re
from datetime import datetime
from . import obsidian
from . import graph
from . import backend
from .graph_index import GraphIndex, get_graph_index
from .graph_filter import FilterConfig, GraphFilter, create_filter_from_args
from .graph_ranker import RankingConfig, GraphRanker, create_ranker_from_args

api_key = os.getenv("OBSIDIAN_API_KEY", "")
obsidian_host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")

if api_key == "":
    raise ValueError(f"OBSIDIAN_API_KEY environment variable required. Working directory: {os.getcwd()}")

TOOL_LIST_FILES_IN_VAULT = "obsidian_list_files_in_vault"
TOOL_LIST_FILES_IN_DIR = "obsidian_list_files_in_dir"

class ToolHandler():
    def __init__(self, tool_name: str):
        self.name = tool_name

    def get_tool_description(self) -> Tool:
        raise NotImplementedError()

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        raise NotImplementedError()
    
class ListFilesInVaultToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_LIST_FILES_IN_VAULT)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all files and directories in the root directory of your Obsidian vault.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            },
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        files = api.list_files_in_vault()

        return [
            TextContent(
                type="text",
                text=json.dumps(files, indent=2)
            )
        ]
    
class ListFilesInDirToolHandler(ToolHandler):
    def __init__(self):
        super().__init__(TOOL_LIST_FILES_IN_DIR)

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Lists all files and directories that exist in a specific Obsidian directory.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dirpath": {
                        "type": "string",
                        "description": "Path to list files from (relative to your vault root). Note that empty directories will not be returned."
                    },
                },
                "required": ["dirpath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:

        if "dirpath" not in args:
            raise RuntimeError("dirpath argument missing in arguments")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        files = api.list_files_in_dir(args["dirpath"])

        return [
            TextContent(
                type="text",
                text=json.dumps(files, indent=2)
            )
        ]
    
class GetFileContentsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_file_contents")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Return the content of a single file in your vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the relevant file (relative to your vault root).",
                        "format": "path"
                    },
                },
                "required": ["filepath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args:
            raise RuntimeError("filepath argument missing in arguments")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        content = api.get_file_contents(args["filepath"])

        return [
            TextContent(
                type="text",
                text=json.dumps(content, indent=2)
            )
        ]
    
class SearchToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_simple_search")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="""Simple search for documents matching a specified text query across all files in the vault. 
            Use this tool when you want to do a simple text search""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to a simple search for in the vault."
                    },
                    "context_length": {
                        "type": "integer",
                        "description": "How much context to return around the matching string (default: 100)",
                        "default": 100
                    }
                },
                "required": ["query"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "query" not in args:
            raise RuntimeError("query argument missing in arguments")

        context_length = args.get("context_length", 100)
        
        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        results = api.search(args["query"], context_length)
        
        formatted_results = []
        for result in results:
            formatted_matches = []
            for match in result.get('matches', []):
                context = match.get('context', '')
                match_pos = match.get('match', {})
                start = match_pos.get('start', 0)
                end = match_pos.get('end', 0)
                
                formatted_matches.append({
                    'context': context,
                    'match_position': {'start': start, 'end': end}
                })
                
            formatted_results.append({
                'filename': result.get('filename', ''),
                'score': result.get('score', 0),
                'matches': formatted_matches
            })

        return [
            TextContent(
                type="text",
                text=json.dumps(formatted_results, indent=2)
            )
        ]
    
class AppendContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_append_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="Append content to a new or existing file in the vault.",
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   },
                   "content": {
                       "type": "string",
                       "description": "Content to append to the file"
                   }
               },
               "required": ["filepath", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args or "content" not in args:
           raise RuntimeError("filepath and content arguments required")

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       api.append_content(args.get("filepath", ""), args["content"])

       return [
           TextContent(
               type="text",
               text=f"Successfully appended content to {args['filepath']}"
           )
       ]
   
class PatchContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_patch_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="Insert content into an existing note relative to a heading, block reference, or frontmatter field.",
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file (relative to vault root)",
                       "format": "path"
                   },
                   "operation": {
                       "type": "string",
                       "description": "Operation to perform (append, prepend, or replace)",
                       "enum": ["append", "prepend", "replace"]
                   },
                   "target_type": {
                       "type": "string",
                       "description": "Type of target to patch",
                       "enum": ["heading", "block", "frontmatter"]
                   },
                   "target": {
                       "type": "string", 
                       "description": "Target identifier (heading path, block reference, or frontmatter field)"
                   },
                   "content": {
                       "type": "string",
                       "description": "Content to insert"
                   }
               },
               "required": ["filepath", "operation", "target_type", "target", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if not all(k in args for k in ["filepath", "operation", "target_type", "target", "content"]):
           raise RuntimeError("filepath, operation, target_type, target and content arguments required")

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       api.patch_content(
           args.get("filepath", ""),
           args.get("operation", ""),
           args.get("target_type", ""),
           args.get("target", ""),
           args.get("content", "")
       )

       return [
           TextContent(
               type="text",
               text=f"Successfully patched content in {args['filepath']}"
           )
       ]
       
class PutContentToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_put_content")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="Create a new file in your vault or update the content of an existing one in your vault.",
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the relevant file (relative to your vault root)",
                       "format": "path"
                   },
                   "content": {
                       "type": "string",
                       "description": "Content of the file you would like to upload"
                   }
               },
               "required": ["filepath", "content"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args or "content" not in args:
           raise RuntimeError("filepath and content arguments required")

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       api.put_content(args.get("filepath", ""), args["content"])

       return [
           TextContent(
               type="text",
               text=f"Successfully uploaded content to {args['filepath']}"
           )
       ]
   

class DeleteFileToolHandler(ToolHandler):
   def __init__(self):
       super().__init__("obsidian_delete_file")

   def get_tool_description(self):
       return Tool(
           name=self.name,
           description="Delete a file or directory from the vault.",
           inputSchema={
               "type": "object",
               "properties": {
                   "filepath": {
                       "type": "string",
                       "description": "Path to the file or directory to delete (relative to vault root)",
                       "format": "path"
                   },
                   "confirm": {
                       "type": "boolean",
                       "description": "Confirmation to delete the file (must be true)",
                       "default": False
                   }
               },
               "required": ["filepath", "confirm"]
           }
       )

   def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
       if "filepath" not in args:
           raise RuntimeError("filepath argument missing in arguments")
       
       if not args.get("confirm", False):
           raise RuntimeError("confirm must be set to true to delete a file")

       api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
       api.delete_file(args["filepath"])

       return [
           TextContent(
               type="text",
               text=f"Successfully deleted {args['filepath']}"
           )
       ]
   
class BatchGetFileContentsToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_batch_get_file_contents")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Return the contents of multiple files in your vault, concatenated with headers.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepaths": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "description": "Path to a file (relative to your vault root)",
                            "format": "path"
                        },
                        "description": "List of file paths to read"
                    },
                },
                "required": ["filepaths"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepaths" not in args:
            raise RuntimeError("filepaths argument missing in arguments")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        content = api.get_batch_file_contents(args["filepaths"])

        return [
            TextContent(
                type="text",
                text=content
            )
        ]

class PeriodicNotesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_periodic_note")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get current periodic note for the specified period.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "The period type (daily, weekly, monthly, quarterly, yearly)",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"]
                    },
                    "type": {
                        "type": "string",
                        "description": "The type of data to get ('content' or 'metadata'). 'content' returns just the content in Markdown format. 'metadata' includes note metadata (including paths, tags, etc.) and the content.",
                        "default": "content",
                        "enum": ["content", "metadata"]
                    }
                },
                "required": ["period"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "period" not in args:
            raise RuntimeError("period argument missing in arguments")

        period = args["period"]
        valid_periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if period not in valid_periods:
            raise RuntimeError(f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}")
        
        type = args["type"] if "type" in args else "content"
        valid_types = ["content", "metadata"]
        if type not in valid_types:
            raise RuntimeError(f"Invalid type: {type}. Must be one of: {', '.join(valid_types)}")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        content = api.get_periodic_note(period,type)

        return [
            TextContent(
                type="text",
                text=content
            )
        ]
        
class RecentPeriodicNotesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_recent_periodic_notes")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get most recent periodic notes for the specified period type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": "The period type (daily, weekly, monthly, quarterly, yearly)",
                        "enum": ["daily", "weekly", "monthly", "quarterly", "yearly"]
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of notes to return (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 50
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Whether to include note content (default: false)",
                        "default": False
                    }
                },
                "required": ["period"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "period" not in args:
            raise RuntimeError("period argument missing in arguments")

        period = args["period"]
        valid_periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]
        if period not in valid_periods:
            raise RuntimeError(f"Invalid period: {period}. Must be one of: {', '.join(valid_periods)}")

        limit = args.get("limit", 5)
        if not isinstance(limit, int) or limit < 1:
            raise RuntimeError(f"Invalid limit: {limit}. Must be a positive integer")
            
        include_content = args.get("include_content", False)
        if not isinstance(include_content, bool):
            raise RuntimeError(f"Invalid include_content: {include_content}. Must be a boolean")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        results = api.get_recent_periodic_notes(period, limit, include_content)

        return [
            TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )
        ]
        
class RecentChangesToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_recent_changes")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get recently modified files in the vault.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of files to return (default: 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100
                    },
                    "days": {
                        "type": "integer",
                        "description": "Only include files modified within this many days (default: 90)",
                        "minimum": 1,
                        "default": 90
                    }
                }
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        limit = args.get("limit", 10)
        if not isinstance(limit, int) or limit < 1:
            raise RuntimeError(f"Invalid limit: {limit}. Must be a positive integer")
            
        days = args.get("days", 90)
        if not isinstance(days, int) or days < 1:
            raise RuntimeError(f"Invalid days: {days}. Must be a positive integer")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)
        results = api.get_recent_changes(limit, days)

        return [
            TextContent(
                type="text",
                text=json.dumps(results, indent=2)
            )
        ]

class GetNoteGraphToolHandler(ToolHandler):
    """
    Traverse the link graph with filtering, ranking, and cached index support.

    Enhanced with:
    - Cached graph index for O(1) backlink queries
    - Tag, frontmatter, path, and date filtering
    - PageRank + recency ranking (aligned with smart search P1)
    """

    # Cached graph index (lazy initialization)
    _graph_index: GraphIndex = None

    def __init__(self):
        super().__init__("obsidian_get_note_graph")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Traverse the link graph from a known note to discover connected ideas. Returns neighbors with snippets showing why notes are connected. Best for: exploring context around a specific note, building conceptual maps, understanding note relationships. Use max_hops=1 for direct neighbors (fast), max_hops=2 for comprehensive exploration.",
            inputSchema={
                "type": "object",
                "properties": {
                    # Core parameters (unchanged for backward compatibility)
                    "note_path": {
                        "type": "string",
                        "description": "Path to the starting note (e.g., 'Notes/Programs/Intent/Intent AI Home.md')"
                    },
                    "max_hops": {
                        "type": "integer",
                        "description": "Maximum number of link hops to traverse (1 or 2)",
                        "enum": [1, 2],
                        "default": 1
                    },
                    "max_nodes": {
                        "type": "integer",
                        "description": "Maximum number of connected notes to return (default: 30)",
                        "default": 30,
                        "minimum": 5,
                        "maximum": 100
                    },
                    "snippet_length": {
                        "type": "integer",
                        "description": "Number of characters to include in snippets (default: 200)",
                        "default": 200,
                        "minimum": 50,
                        "maximum": 500
                    },
                    # Filter parameters (new)
                    "filter_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags (e.g., ['project', 'active'])"
                    },
                    "filter_tags_match_all": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, require ALL tags. If false (default), ANY tag matches."
                    },
                    "filter_frontmatter": {
                        "type": "object",
                        "description": "Filter by frontmatter fields (e.g., {'pageType': 'daily', 'status': 'active'})"
                    },
                    "filter_include_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Include only paths matching these glob patterns (e.g., ['Projects/*', 'Work/*'])"
                    },
                    "filter_exclude_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exclude paths matching these patterns (e.g., ['Archive/*', 'Templates/*'])"
                    },
                    "filter_created_after": {
                        "type": "string",
                        "description": "Include only notes created after this date (YYYY-MM-DD)"
                    },
                    "filter_created_before": {
                        "type": "string",
                        "description": "Include only notes created before this date (YYYY-MM-DD)"
                    },
                    "filter_modified_after": {
                        "type": "string",
                        "description": "Include only notes modified after this date (YYYY-MM-DD)"
                    },
                    "filter_modified_before": {
                        "type": "string",
                        "description": "Include only notes modified before this date (YYYY-MM-DD)"
                    },
                    # Ranking parameters (new)
                    "enable_pagerank": {
                        "type": "boolean",
                        "default": True,
                        "description": "Enable PageRank scoring for importance"
                    },
                    "enable_recency": {
                        "type": "boolean",
                        "default": True,
                        "description": "Enable recency weighting (recent notes ranked higher)"
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["relevance", "recency", "pagerank", "hop_distance"],
                        "default": "relevance",
                        "description": "Sort results by: relevance (PageRank+recency), recency, pagerank, or hop_distance"
                    }
                },
                "required": ["note_path"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "note_path" not in args:
            raise RuntimeError("note_path argument missing in arguments")

        note_path = args["note_path"]
        max_hops = args.get("max_hops", 1)
        max_nodes = args.get("max_nodes", 30)
        snippet_length = args.get("snippet_length", 200)
        sort_by = args.get("sort_by", "relevance")

        if max_hops not in (1, 2):
            raise RuntimeError(f"max_hops must be 1 or 2, got {max_hops}")

        if not isinstance(max_nodes, int) or max_nodes < 5:
            raise RuntimeError(f"max_nodes must be at least 5, got {max_nodes}")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        # Get all files in vault for path resolution
        try:
            all_files = api.list_files_in_vault()
            file_paths = []
            if isinstance(all_files, list):
                for f in all_files:
                    if isinstance(f, dict):
                        if f.get('type') == 'file' and 'path' in f:
                            file_paths.append(f['path'])
                    elif isinstance(f, str):
                        file_paths.append(f)
        except Exception as e:
            raise RuntimeError(f"Failed to list vault files: {str(e)}")

        # Get or build graph index (lazy initialization)
        # TODO: Load exclude_paths from config for "Do Not Search" folders
        graph_index = get_graph_index(
            file_getter=api.get_file_contents,
            all_files=file_paths,
            exclude_paths=args.get("filter_exclude_paths")
        )

        # Create filter config from args
        filter_config = create_filter_from_args(args)
        graph_filter = GraphFilter(filter_config) if filter_config else None

        # Traverse the graph using index for backlinks
        result = self._traverse_with_index(
            start_path=note_path,
            file_paths=file_paths,
            graph_index=graph_index,
            graph_filter=graph_filter,
            file_getter=api.get_file_contents,
            max_hops=max_hops,
            max_nodes=max_nodes,
            snippet_length=snippet_length
        )

        # Apply ranking
        ranker = create_ranker_from_args(args)
        result['nodes'] = ranker.rank(
            nodes=result['nodes'],
            pagerank_scores=graph_index.pagerank_scores,
            sort_by=sort_by
        )

        # Add summary info
        result['summary']['filters_applied'] = (
            filter_config.get_applied_filters() if filter_config else []
        )
        result['summary']['graph_stats'] = graph_index.get_stats()

        return [
            TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )
        ]

    def _traverse_with_index(
        self,
        start_path: str,
        file_paths: list,
        graph_index: GraphIndex,
        graph_filter: GraphFilter,
        file_getter: callable,
        max_hops: int,
        max_nodes: int,
        snippet_length: int
    ) -> dict:
        """
        Traverse graph using cached index for O(1) backlink queries.
        """
        from collections import deque

        visited = set()
        queue = deque([(start_path, 0)])  # (path, hop_distance)
        result_nodes = {}
        result_edges = []

        while queue and len(result_nodes) < max_nodes:
            current_path, hop = queue.popleft()

            if current_path in visited:
                continue

            visited.add(current_path)

            # Get metadata from index
            metadata = graph_index.get_metadata(current_path)

            # Apply filter (skip if doesn't match)
            if graph_filter and not graph_filter.matches(current_path, metadata):
                continue

            # Get content for snippet
            try:
                content = file_getter(current_path)
                if not isinstance(content, str):
                    continue
            except Exception:
                continue

            # Extract snippet
            snippet = content[:snippet_length].strip()
            if len(content) > snippet_length:
                last_period = snippet.rfind('.')
                if last_period > 0:
                    snippet = snippet[:last_period + 1]

            # Build node data
            node_data = {
                'path': current_path,
                'title': metadata.get('title', current_path),
                'word_count': metadata.get('word_count', 0),
                'snippet': snippet,
                'hop_distance': hop,
                'tags': metadata.get('tags', []),
                'frontmatter': metadata.get('frontmatter', {}),
                'created': metadata.get('created'),
                'modified': metadata.get('modified')
            }
            result_nodes[current_path] = node_data

            # Get neighbors using index (O(1) lookups)
            if hop < max_hops:
                # Forward links
                for target_path in graph_index.get_forward_links(current_path):
                    if target_path not in visited:
                        result_edges.append({
                            'from': current_path,
                            'to': target_path,
                            'type': 'wikilink',
                            'link_text': ''
                        })
                        queue.append((target_path, hop + 1))

                # Backlinks (O(1) with index!)
                for source_path in graph_index.get_backlinks(current_path):
                    if source_path not in visited:
                        result_edges.append({
                            'from': source_path,
                            'to': current_path,
                            'type': 'wikilink',
                            'link_text': ''
                        })
                        queue.append((source_path, hop + 1))

        return {
            'center_node': {
                'path': start_path,
                'title': result_nodes.get(start_path, {}).get('title', '')
            },
            'nodes': list(result_nodes.values()),
            'edges': result_edges,
            'summary': {
                'total_nodes': len(result_nodes),
                'total_edges': len(result_edges),
                'max_hops': max_hops
            }
        }


class GetActiveFileToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_get_active_file")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Get the currently active (open) file in Obsidian. Returns the file path, content, and optionally metadata like frontmatter and tags.",
            inputSchema={
                "type": "object",
                "properties": {
                    "format": {
                        "type": "string",
                        "description": "Return format: 'markdown' for raw content, 'json' for structured data with frontmatter, tags, and file stats",
                        "enum": ["markdown", "json"],
                        "default": "json"
                    }
                }
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        format_type = args.get("format", "json")
        if format_type not in ("markdown", "json"):
            raise RuntimeError(f"Invalid format: {format_type}. Must be 'markdown' or 'json'")

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        try:
            result = api.get_active_file(format=format_type)

            if format_type == "json":
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(result, indent=2)
                    )
                ]
            else:
                return [
                    TextContent(
                        type="text",
                        text=result
                    )
                ]
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg:
                raise RuntimeError("No file is currently active in Obsidian")
            raise RuntimeError(f"Failed to get active file: {error_msg}")


class ShowFileToolHandler(ToolHandler):
    def __init__(self):
        super().__init__("obsidian_show_file")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="Open a file in Obsidian's UI. If the file doesn't exist, Obsidian will create it.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {
                        "type": "string",
                        "description": "Path to the file (relative to vault root)",
                        "format": "path"
                    },
                    "new_leaf": {
                        "type": "boolean",
                        "description": "If true, open in a new pane/tab instead of replacing the current view",
                        "default": False
                    }
                },
                "required": ["filepath"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "filepath" not in args:
            raise RuntimeError("filepath argument missing in arguments")

        filepath = args["filepath"]
        new_leaf = args.get("new_leaf", False)

        api = obsidian.Obsidian(api_key=api_key, host=obsidian_host)

        try:
            api.open_file(filepath, new_leaf=new_leaf)
            return [
                TextContent(
                    type="text",
                    text=f"Successfully opened {filepath} in Obsidian"
                )
            ]
        except Exception as e:
            raise RuntimeError(f"Failed to open file: {str(e)}")


class SmartSearchToolHandler(ToolHandler):
    """Smart semantic search with hybrid ranking (dense + BM25 + recency)."""

    def __init__(self):
        super().__init__("obsidian_smart_search")

    def get_tool_description(self):
        return Tool(
            name=self.name,
            description="""Smart semantic search across your Obsidian vault using hybrid ranking.

Combines dense embeddings (EmbeddingGemma), BM25 keyword matching, and recency weighting.
Uses benchmark-validated hierarchical chunking (H1-H6 headings).
Returns chunked results (not full notes) for precise retrieval.

Modes:
- default: Balanced for daily use (MRR@5: 0.6374)
- research: Higher semantic weight for deep research (MRR@5: 0.6316)
- unweighted: Pure hybrid without recency""",
            inputSchema={
                "type": "object",
                "properties": {
                    # Core search parameters
                    "query": {
                        "type": "string",
                        "description": "Search query - can be a question, keywords, or natural language"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20
                    },
                    "mode": {
                        "type": "string",
                        "description": "Ranking mode: 'default', 'research', or 'unweighted'",
                        "enum": ["default", "research", "unweighted"],
                        "default": "default"
                    },
                    # Filter parameters (aligned with graph tool)
                    "filter_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags (e.g., ['project', 'active'])"
                    },
                    "filter_tags_match_all": {
                        "type": "boolean",
                        "default": False,
                        "description": "If true, require ALL tags. If false (default), ANY tag matches."
                    },
                    "filter_frontmatter": {
                        "type": "object",
                        "description": "Filter by frontmatter fields (e.g., {'pageType': 'daily', 'status': 'active'})"
                    },
                    "filter_include_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Include only paths matching these glob patterns (e.g., ['Projects/*', 'Work/*'])"
                    },
                    "filter_exclude_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exclude paths matching these patterns (e.g., ['Archive/*', 'Templates/*'])"
                    },
                    "filter_created_after": {
                        "type": "string",
                        "description": "Include only notes created after this date (YYYY-MM-DD)"
                    },
                    "filter_created_before": {
                        "type": "string",
                        "description": "Include only notes created before this date (YYYY-MM-DD)"
                    },
                    "filter_modified_after": {
                        "type": "string",
                        "description": "Include only notes modified after this date (YYYY-MM-DD)"
                    },
                    "filter_modified_before": {
                        "type": "string",
                        "description": "Include only notes modified before this date (YYYY-MM-DD)"
                    }
                },
                "required": ["query"]
            }
        )

    def run_tool(self, args: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        if "query" not in args:
            raise RuntimeError("query argument missing in arguments")

        query = args["query"]
        top_k = args.get("top_k", 5)
        mode = args.get("mode", "default")

        # Build request payload
        payload = {
            "query": query,
            "top_k": top_k,
            "mode": mode,
        }

        # Add filter parameters if provided
        filters = {}
        if args.get("filter_tags"):
            filters["tags"] = args["filter_tags"]
            filters["tags_match_all"] = args.get("filter_tags_match_all", False)
        if args.get("filter_frontmatter"):
            filters["frontmatter"] = args["filter_frontmatter"]
        if args.get("filter_include_paths"):
            filters["include_paths"] = args["filter_include_paths"]
        if args.get("filter_exclude_paths"):
            filters["exclude_paths"] = args["filter_exclude_paths"]
        if args.get("filter_created_after"):
            filters["created_after"] = args["filter_created_after"]
        if args.get("filter_created_before"):
            filters["created_before"] = args["filter_created_before"]
        if args.get("filter_modified_after"):
            filters["modified_after"] = args["filter_modified_after"]
        if args.get("filter_modified_before"):
            filters["modified_before"] = args["filter_modified_before"]

        if filters:
            payload["filters"] = filters

        # Forward request to RAG backend
        try:
            proxy = backend.get_backend_proxy()
            result = proxy.post("/api/smart-search-vault", payload)

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )
            ]
        except Exception as e:
            raise RuntimeError(f"Smart search failed: {str(e)}")
