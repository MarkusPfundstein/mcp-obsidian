import re
import requests
import urllib.parse
import os
import posixpath
from typing import Any


def validate_vault_path(path: str, is_dir: bool = False) -> str:
    """Validate and normalize a path relative to the Obsidian vault root.

    Prevents directory traversal attacks, absolute paths, and URL-encoding bypasses.

    Args:
        path: Path string relative to vault root.
        is_dir: True if the path represents a directory (allows empty string for vault root).

    Returns:
        The normalized relative path without leading/trailing slashes.

    Raises:
        ValueError: If path is invalid, absolute, attempts directory traversal,
                    or resolves outside the vault root.
    """
    if not isinstance(path, str):
        raise ValueError(f"Vault path must be a string, got {type(path).__name__}")

    cleaned = path.strip()
    if not cleaned or (is_dir and cleaned in (".", "/")):
        if is_dir:
            return ""
        raise ValueError("Filepath cannot be empty")

    # Multi-pass URL decoding to defeat nested/double URL encoding (e.g. %252e%252e).
    # The cap is a fail-closed guard: if the value is still changing after the
    # last pass, deeper encoding remains and downstream stages could decode it
    # into something we did not validate, so reject it.
    decoded = cleaned
    for _ in range(5):
        try:
            next_decoded = urllib.parse.unquote(decoded, errors="strict")
        except UnicodeDecodeError:
            # Invalid UTF-8 percent-escapes (e.g. overlong sequences like
            # %c0%af that some decoders normalize to '/' or '.') must never
            # reach the server, where they could be interpreted as separators.
            raise ValueError(f"Path contains invalid UTF-8 percent-encoding: {path!r}") from None
        if next_decoded == decoded:
            break
        decoded = next_decoded
    else:
        try:
            if urllib.parse.unquote(decoded, errors="strict") != decoded:
                raise ValueError(f"Path has excessively nested URL encoding: {path!r}")
        except UnicodeDecodeError:
            raise ValueError(f"Path contains invalid UTF-8 percent-encoding: {path!r}") from None

    # Reject null bytes (raw or previously URL-encoded)
    if "\x00" in decoded:
        raise ValueError(f"Path contains null bytes: {path!r}")

    # Normalize Windows backslashes to forward slashes
    normalized_separators = decoded.replace("\\", "/")

    # Reject Windows drive letters (e.g., C:, D:)
    if re.match(r"^[a-zA-Z]:", normalized_separators):
        raise ValueError(f"Absolute Windows paths are not allowed: {path!r}")

    # Reject absolute paths (starting with /)
    if normalized_separators.startswith("/"):
        raise ValueError(f"Absolute paths are not allowed: {path!r}")

    # Check for path traversal in segments
    segments = normalized_separators.split("/")
    for segment in segments:
        if segment == "..":
            raise ValueError(f"Path traversal ('..') is not allowed: {path!r}")

    # Normalization check using posixpath.normpath
    norm = posixpath.normpath(normalized_separators)
    if norm == ".." or norm.startswith("../") or "/../" in norm or norm.startswith("/"):
        raise ValueError(f"Path resolves outside vault root: {path!r}")

    if norm == ".":
        if is_dir:
            return ""
        raise ValueError("Filepath cannot be empty")

    return norm


class Obsidian():
    def __init__(
            self, 
            api_key: str,
            protocol: str = os.getenv('OBSIDIAN_PROTOCOL', 'https').lower(),
            host: str = str(os.getenv('OBSIDIAN_HOST', '127.0.0.1')),
            port: int = int(os.getenv('OBSIDIAN_PORT', '27124')),
            verify_ssl: bool = False,
        ):
        self.api_key = api_key
        
        if protocol == 'http':
            self.protocol = 'http'
        else:
            self.protocol = 'https' # Default to https for any other value, including 'https'

        self.host = host
        self.port = port
        self.verify_ssl = verify_ssl
        self.timeout = (3, 6)

    def get_base_url(self) -> str:
        return f'{self.protocol}://{self.host}:{self.port}'

    def _vault_url(self, path: str, is_dir: bool = False) -> str:
        clean_path = validate_vault_path(path, is_dir=is_dir)
        quoted = urllib.parse.quote(clean_path, safe="/")
        if is_dir:
            return f"{self.get_base_url()}/vault/{quoted}/" if quoted else f"{self.get_base_url()}/vault/"
        return f"{self.get_base_url()}/vault/{quoted}"
    
    def _get_headers(self) -> dict:
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        return headers

    def _safe_call(self, f) -> Any:
        try:
            return f()
        except requests.HTTPError as e:
            error_data = {}
            if e.response is not None and e.response.content:
                try:
                    parsed = e.response.json()
                    if isinstance(parsed, dict):
                        error_data = parsed
                except ValueError:
                    pass
            code = error_data.get('errorCode', -1) 
            message = error_data.get('message', '<unknown>')
            raise Exception(f"Error {code}: {message}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def list_files_in_vault(self) -> Any:
        url = f"{self.get_base_url()}/vault/"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            return response.json()['files']

        return self._safe_call(call_fn)

        
    def list_files_in_dir(self, dirpath: str) -> Any:
        url = self._vault_url(dirpath, is_dir=True)
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            return response.json()['files']

        return self._safe_call(call_fn)

    def get_file_contents(self, filepath: str) -> Any:
        url = self._vault_url(filepath, is_dir=False)
    
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            return response.text

        return self._safe_call(call_fn)
    
    def get_batch_file_contents(self, filepaths: list[str]) -> str:
        """Get contents of multiple files and concatenate them with headers.
        
        Args:
            filepaths: List of file paths to read
            
        Returns:
            String containing all file contents with headers
        """
        result = []
        
        for filepath in filepaths:
            try:
                content = self.get_file_contents(filepath)
                result.append(f"# {filepath}\n\n{content}\n\n---\n\n")
            except Exception as e:
                # Add error message but continue processing other files
                result.append(f"# {filepath}\n\nError reading file: {str(e)}\n\n---\n\n")
                
        return "".join(result)

    def search(self, query: str, context_length: int = 100) -> Any:
        url = f"{self.get_base_url()}/search/simple/"
        params = {
            'query': query,
            'contextLength': context_length
        }
        
        def call_fn():
            response = requests.post(url, headers=self._get_headers(), params=params, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)
    
    def append_content(self, filepath: str, content: str) -> Any:
        url = self._vault_url(filepath, is_dir=False)

        def call_fn():
            response = requests.post(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown; charset=utf-8'},
                data=content.encode("utf-8"),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    def patch_content(self, filepath: str, operation: str, target_type: str, target: str, content: str) -> Any:
        try:
            return self._patch_content_raw(filepath, operation, target_type, target, content)
        except Exception as e:
            # The Local REST API requires fully qualified heading paths like
            # "Outer::Inner". If the caller passed a bare heading name and the
            # server replied with 40080 invalid-target, try to auto-qualify by
            # parsing the file's heading hierarchy. See issue #125.
            if target_type != "heading" or "::" in target or "Error 40080" not in str(e):
                raise

            try:
                file_content = self.get_file_contents(filepath)
            except Exception:
                raise e

            candidates = _find_heading_paths(file_content, target)
            if len(candidates) == 1:
                qualified = candidates[0]
                return self._patch_content_raw(filepath, operation, target_type, qualified, content)
            if len(candidates) > 1:
                raise Exception(
                    f"Ambiguous heading '{target}'. Candidates: {', '.join(candidates)}. "
                    "Specify the qualified path with '::' delimiter."
                )
            raise

    def _patch_content_raw(self, filepath: str, operation: str, target_type: str, target: str, content: str) -> Any:
        url = self._vault_url(filepath, is_dir=False)

        # NOTE: The Local REST API rejects 'text/markdown; charset=utf-8' on
        # PATCH (error 40012) — its PATCH parser only accepts the plain
        # 'text/markdown' form. We still send the body as utf-8 bytes so the
        # encoding is unambiguous on the wire.
        headers = self._get_headers() | {
            'Content-Type': 'text/markdown',
            'Operation': operation,
            'Target-Type': target_type,
            'Target': urllib.parse.quote(target)
        }

        def call_fn():
            response = requests.patch(url, headers=headers, data=content.encode("utf-8"), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    def put_content(self, filepath: str, content: str) -> Any:
        url = self._vault_url(filepath, is_dir=False)

        def call_fn():
            response = requests.put(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown; charset=utf-8'},
                data=content.encode("utf-8"),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def delete_file(self, filepath: str) -> Any:
        """Delete a file or directory from the vault.
        
        Args:
            filepath: Path to the file to delete (relative to vault root)
            
        Returns:
            None on success
        """
        url = self._vault_url(filepath, is_dir=False)
        
        def call_fn():
            response = requests.delete(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None
            
        return self._safe_call(call_fn)
    
    def search_json(self, query: dict) -> Any:
        url = f"{self.get_base_url()}/search/"

        headers = self._get_headers() | {
            'Content-Type': 'application/vnd.olrapi.jsonlogic+json'
        }

        def call_fn():
            response = requests.post(url, headers=headers, json=query, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)

    def search_by_tag(self, tag: str, dirpath: str | None = None) -> list[str]:
        """Return paths of all notes carrying the given tag.

        Matches against the parsed tag set (frontmatter `tags:` plus inline
        `#tag` occurrences), so hits on the tag name inside ordinary prose
        do NOT match — unlike `simple_search('#tag')`. The tag should be
        passed without the leading `#`.

        Args:
            tag: Tag name without the leading '#'. Match is exact; the
                hierarchical parent of a `parent/child` tag does NOT match
                `parent` here (the API exposes hierarchy only via /tags/).
            dirpath: Optional vault-relative directory to scope results to,
                e.g. 'work/projects'. Trailing slash is stripped.

        Returns:
            List of matching file paths (vault-relative).
        """
        tag_query: dict = {"in": [tag, {"var": "tags"}]}
        if dirpath:
            clean_dir = validate_vault_path(dirpath, is_dir=True)
            if clean_dir:
                prefix = clean_dir.rstrip("/") + "/"
                query: dict = {
                    "and": [
                        tag_query,
                        {"glob": [f"{prefix}*", {"var": "path"}]},
                    ]
                }
            else:
                query = tag_query
        else:
            query = tag_query
        results = self.search_json(query)
        return [r["filename"] for r in results]

    def get_frontmatter(self, filepath: str) -> dict:
        """Return the parsed frontmatter of a single note as a dict.

        Uses the Local REST API's `application/vnd.olrapi.note+json` view,
        so YAML parsing happens server-side. Returns an empty dict for
        notes without frontmatter; never raises for missing frontmatter
        (only for missing files or transport errors).
        """
        url = self._vault_url(filepath, is_dir=False)
        headers = self._get_headers() | {
            'Accept': 'application/vnd.olrapi.note+json'
        }

        def call_fn():
            response = requests.get(url, headers=headers, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            return payload.get("frontmatter", {}) or {}

        return self._safe_call(call_fn)

    def get_periodic_note(self, period: str, type: str = "content") -> Any:
        """Get current periodic note for the specified period.
        
        Args:
            period: The period type (daily, weekly, monthly, quarterly, yearly)
            type: Type of the data to get ('content' or 'metadata'). 
                'content' returns just the content in Markdown format. 
                'metadata' includes note metadata (including paths, tags, etc.) and the content.. 
            
        Returns:
            Content of the periodic note
        """
        url = f"{self.get_base_url()}/periodic/{period}/"
        
        def call_fn():
            headers = self._get_headers()
            if type == "metadata":
                headers['Accept'] = 'application/vnd.olrapi.note+json'
            response = requests.get(url, headers=headers, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            return response.text

        return self._safe_call(call_fn)
    
    def get_recent_periodic_notes(self, period: str, limit: int = 5, include_content: bool = False) -> Any:
        """Get most recent periodic notes for the specified period type.
        
        Args:
            period: The period type (daily, weekly, monthly, quarterly, yearly)
            limit: Maximum number of notes to return (default: 5)
            include_content: Whether to include note content (default: False)
            
        Returns:
            List of recent periodic notes
        """
        url = f"{self.get_base_url()}/periodic/{period}/recent"
        params = {
            "limit": limit,
            "includeContent": include_content
        }
        
        def call_fn():
            response = requests.get(
                url, 
                headers=self._get_headers(), 
                params=params,
                verify=self.verify_ssl, 
                timeout=self.timeout
            )
            response.raise_for_status()
            
            return response.json()

        return self._safe_call(call_fn)
    
    def get_recent_changes(self, limit: int = 10, days: int = 90) -> Any:
        """Get recently modified files in the vault.
        
        Args:
            limit: Maximum number of files to return (default: 10)
            days: Only include files modified within this many days (default: 90)
            
        Returns:
            List of recently modified files with metadata
        """
        # Build the DQL query
        query_lines = [
            "TABLE file.mtime",
            f"WHERE file.mtime >= date(today) - dur({days} days)",
            "SORT file.mtime DESC",
            f"LIMIT {limit}"
        ]
        
        # Join with proper DQL line breaks
        dql_query = "\n".join(query_lines)
        
        # Make the request to search endpoint
        url = f"{self.get_base_url()}/search/"
        headers = self._get_headers() | {
            'Content-Type': 'application/vnd.olrapi.dataview.dql+txt'
        }
        
        def call_fn():
            response = requests.post(
                url,
                headers=headers,
                data=dql_query.encode('utf-8'),
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        return self._safe_call(call_fn)


_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _find_heading_paths(content: str, target: str) -> list[str]:
    """Return fully-qualified heading paths whose last segment matches target case-insensitively.

    Headings inside fenced code blocks (``` or ~~~) are ignored. The qualified
    path joins all enclosing heading texts with '::' (matching the Local REST
    API's heading-target syntax).
    """
    in_fence = False
    stack: list[tuple[int, str]] = []
    matches: list[str] = []
    target_lower = target.lower()

    for line in content.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        text = re.sub(r"\s+#+\s*$", "", m.group(2)).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, text))
        if text.lower() == target_lower:
            matches.append("::".join(t for _, t in stack))

    return matches
