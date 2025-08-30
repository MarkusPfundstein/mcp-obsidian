import requests
import urllib.parse
from urllib.parse import quote, unquote
import unicodedata
import os
from typing import Any

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
    
    def _get_headers(self) -> dict:
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        return headers

    def _safe_call(self, f) -> Any:
        try:
            return f()
        except requests.HTTPError as e:
            error_data = e.response.json() if e.response.content else {}
            code = error_data.get('errorCode', -1) 
            message = error_data.get('message', '<unknown>')
            raise Exception(f"Error {code}: {message}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def _encode_path(self, path: str) -> str:
        """Encode path segments while preserving directory separators and trailing slashes.
        
        Features:
        - Idempotent: Prevents double-encoding of already encoded paths
        - Unicode normalization: Converts NFD to NFC for consistency  
        - RFC 3986 compliant: Preserves safe characters (-_.~)
        - Preserves directory structure: "/" separators and trailing "/" maintained
        
        Args:
            path: File or directory path (relative to vault root)
            
        Returns:
            URL-encoded path with preserved "/" separators and trailing slash
            
        Examples:
            "simple.md" → "simple.md"
            "Reports/2024/" → "Reports/2024/" (trailing slash preserved)
            "Área/çãõ/test.md" → "%C3%81rea/%C3%A7%C3%A3%C3%B5/test.md"
            "already%20encoded/" → "already%20encoded/" (idempotent)
            "emoji/📘 notes.md" → "emoji/%F0%9F%93%98%20notes.md"
        """
        if not path:
            return ""
        
        # Record if path had trailing slash before processing
        had_trailing_slash = path.endswith('/')
        
        # Split path into segments, removing empty segments  
        segments = [seg for seg in path.strip("/").split("/") if seg]
        
        # RFC 3986 unreserved characters that don't need encoding
        safe_chars = "-_.~"
        
        encoded_segments = []
        for segment in segments:
            # Prevent double-encoding by decoding first
            segment = unquote(segment)
            
            # Normalize Unicode (NFD → NFC) for consistency across platforms
            segment = unicodedata.normalize("NFC", segment)
            
            # Encode segment while preserving safe characters
            encoded_segment = quote(segment, safe=safe_chars)
            encoded_segments.append(encoded_segment)
        
        # Join segments and restore trailing slash if originally present
        encoded_path = "/".join(encoded_segments)
        if had_trailing_slash and encoded_segments:
            encoded_path += "/"
        
        return encoded_path

    def list_files_in_vault(self) -> Any:
        url = f"{self.get_base_url()}/vault/"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            return response.json()['files']

        return self._safe_call(call_fn)

        
    def list_files_in_dir(self, dirpath: str) -> Any:
        encoded_path = self._encode_path(dirpath)
        # Ensure exactly one trailing slash for directory endpoint
        if not encoded_path.endswith('/'):
            encoded_path += '/'
        url = f"{self.get_base_url()}/vault/{encoded_path}"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            return response.json()['files']

        return self._safe_call(call_fn)

    def get_file_contents(self, filepath: str) -> Any:
        encoded_path = self._encode_path(filepath)
        url = f"{self.get_base_url()}/vault/{encoded_path}"
    
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
        encoded_path = self._encode_path(filepath)
        url = f"{self.get_base_url()}/vault/{encoded_path}"
        
        def call_fn():
            response = requests.post(
                url, 
                headers=self._get_headers() | {'Content-Type': 'text/markdown'}, 
                data=content,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def patch_content(self, filepath: str, operation: str, target_type: str, target: str, content: str) -> Any:
        encoded_path = self._encode_path(filepath)
        url = f"{self.get_base_url()}/vault/{encoded_path}"
        
        headers = self._get_headers() | {
            'Content-Type': 'text/markdown',
            'Operation': operation,
            'Target-Type': target_type,
            'Target': urllib.parse.quote(target)
        }
        
        def call_fn():
            response = requests.patch(url, headers=headers, data=content, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)

    def put_content(self, filepath: str, content: str) -> Any:
        encoded_path = self._encode_path(filepath)
        url = f"{self.get_base_url()}/vault/{encoded_path}"
        
        def call_fn():
            response = requests.put(
                url, 
                headers=self._get_headers() | {'Content-Type': 'text/markdown'}, 
                data=content,
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
        encoded_path = self._encode_path(filepath)
        url = f"{self.get_base_url()}/vault/{encoded_path}"
        
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
    
    def get_periodic_note(self, period: str, as_json: bool = False) -> Any:
        """Get current periodic note for the specified period.
        
        Args:
            period: The period type (daily, weekly, monthly, quarterly, yearly)
            as_json: Whether to return JSON format with metadata (default: False)
            
        Returns:
            Content of the periodic note (text or JSON)
        """
        url = f"{self.get_base_url()}/periodic/{period}/"
        
        def call_fn():
            headers = self._get_headers()
            if as_json:
                headers['Accept'] = 'application/vnd.olrapi.note+json'
            response = requests.get(url, headers=headers, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            if as_json:
                return response.json()
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
    
    def get_active_note(self, as_json: bool = False) -> Any:
        """Get content of the currently active note in Obsidian.
        
        Args:
            as_json: Whether to return JSON format with metadata (default: False)
            
        Returns:
            Content of the active note (text or JSON)
        """
        url = f"{self.get_base_url()}/active/"
        
        def call_fn():
            headers = self._get_headers()
            if as_json:
                headers['Accept'] = 'application/vnd.olrapi.note+json'
            response = requests.get(url, headers=headers, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            if as_json:
                return response.json()
            return response.text

        return self._safe_call(call_fn)
    
    def append_to_active(self, content: str) -> Any:
        """Append content to the currently active note.
        
        Args:
            content: Content to append to the active note
            
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/active/"
        
        def call_fn():
            response = requests.post(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                data=content,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def replace_active_note(self, content: str) -> Any:
        """Replace entire content of the currently active note.
        
        Args:
            content: New content for the active note
            
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/active/"
        
        def call_fn():
            response = requests.put(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                data=content,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def patch_active_note(self, operation: str, target_type: str, target: str, content: str) -> Any:
        """Insert/replace content in active note relative to a target.
        
        Args:
            operation: Operation to perform (append, prepend, or replace)
            target_type: Type of target (heading, block, or frontmatter)
            target: Target identifier
            content: Content to insert
            
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/active/"
        
        headers = self._get_headers() | {
            'Content-Type': 'text/markdown',
            'Operation': operation,
            'Target-Type': target_type,
            'Target': urllib.parse.quote(target)
        }
        
        def call_fn():
            response = requests.patch(url, headers=headers, data=content, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def delete_active_note(self) -> Any:
        """Delete the currently active note.
        
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/active/"
        
        def call_fn():
            response = requests.delete(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def append_to_periodic(self, period: str, content: str) -> Any:
        """Append content to the current periodic note.
        
        Args:
            period: The period type (daily, weekly, monthly, quarterly, yearly)
            content: Content to append to the periodic note
            
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/periodic/{period}/"
        
        def call_fn():
            response = requests.post(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                data=content,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def replace_periodic_note(self, period: str, content: str) -> Any:
        """Replace entire content of the current periodic note.
        
        Args:
            period: The period type (daily, weekly, monthly, quarterly, yearly)
            content: New content for the periodic note
            
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/periodic/{period}/"
        
        def call_fn():
            response = requests.put(
                url,
                headers=self._get_headers() | {'Content-Type': 'text/markdown'},
                data=content,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def patch_periodic_note(self, period: str, operation: str, target_type: str, target: str, content: str) -> Any:
        """Insert/replace content in periodic note relative to a target.
        
        Args:
            period: The period type (daily, weekly, monthly, quarterly, yearly)
            operation: Operation to perform (append, prepend, or replace)
            target_type: Type of target (heading, block, or frontmatter)
            target: Target identifier
            content: Content to insert
            
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/periodic/{period}/"
        
        headers = self._get_headers() | {
            'Content-Type': 'text/markdown',
            'Operation': operation,
            'Target-Type': target_type,
            'Target': urllib.parse.quote(target)
        }
        
        def call_fn():
            response = requests.patch(url, headers=headers, data=content, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def delete_periodic_note(self, period: str) -> Any:
        """Delete the current periodic note.
        
        Args:
            period: The period type (daily, weekly, monthly, quarterly, yearly)
            
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/periodic/{period}/"
        
        def call_fn():
            response = requests.delete(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def list_commands(self) -> Any:
        """List all available Obsidian commands from the command palette.
        
        Returns:
            List of available commands with their IDs and names
        """
        url = f"{self.get_base_url()}/commands/"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
            
        return self._safe_call(call_fn)
    
    def execute_command(self, command_id: str) -> Any:
        """Execute a specific Obsidian command by its ID.
        
        Args:
            command_id: The ID of the command to execute
            
        Returns:
            None on success
            
        Warning:
            Some commands may be destructive or change Obsidian settings.
            Use with caution and verify command IDs with list_commands().
        """
        url = f"{self.get_base_url()}/commands/{urllib.parse.quote(command_id)}/"
        
        def call_fn():
            response = requests.post(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None
            
        return self._safe_call(call_fn)
    
    def open_file(self, filename: str, new_leaf: bool = False) -> Any:
        """Open a file in Obsidian UI.
        
        Args:
            filename: Path to the file to open (relative to vault root)
            new_leaf: If True, opens in new tab/pane; if False, opens in current view
            
        Returns:
            None on success
        """
        encoded_filename = self._encode_path(filename)
        url = f"{self.get_base_url()}/open/{encoded_filename}"
        params = {"newLeaf": str(new_leaf).lower()}
        
        def call_fn():
            response = requests.post(url, headers=self._get_headers(), params=params, verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None
            
        return self._safe_call(call_fn)
