import requests
import urllib.parse
from typing import Any

class Obsidian():
    def __init__(
            self, 
            api_key: str,
            protocol: str = 'https',
            host: str = "127.0.0.1",
            port: int = 27124,
            verify_ssl: bool = False,
        ):
        self.api_key = api_key
        self.protocol = protocol
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

    def list_files_in_vault(self) -> Any:
        url = f"{self.get_base_url()}/vault/"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            return response.json()['files']

        return self._safe_call(call_fn)

        
    def list_files_in_dir(self, dirpath: str) -> Any:
        url = f"{self.get_base_url()}/vault/{dirpath}/"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            
            return response.json()['files']

        return self._safe_call(call_fn)

    def get_file_contents(self, filepath: str) -> Any:
        url = f"{self.get_base_url()}/vault/{filepath}"
    
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
        url = f"{self.get_base_url()}/vault/{filepath}"
        
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
        url = f"{self.get_base_url()}/vault/{filepath}"
        
        def call_fn():
            # Resolve target based on type and format
            resolved_target = target
            
            # For headings, we need to resolve the full path if only partial heading is provided
            if target_type == "heading" and "::" not in target:
                # If target looks like a heading (starts with #), we need to resolve full path
                if target.startswith("#"):
                    # Get file content to build full heading path
                    try:
                        file_content = self.get_file_contents(filepath)
                        resolved_target = self._resolve_full_heading_path(file_content, target)
                    except Exception:
                        # If we can't resolve, try the original target
                        resolved_target = target
            
            # Check if target contains non-ASCII characters that need URL encoding
            try:
                resolved_target.encode('ascii')
                # Target is pure ASCII, use as-is
                final_target = resolved_target
            except UnicodeEncodeError:
                # Target contains non-ASCII characters, URL encode it
                final_target = urllib.parse.quote(resolved_target, safe='')
            
            headers = self._get_headers() | {
                'Content-Type': 'text/markdown',
                'Operation': operation,
                'Target-Type': target_type,
                'Target': final_target
            }
            
            response = requests.patch(url, headers=headers, data=content.encode('utf-8'), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()
            return None

        return self._safe_call(call_fn)
    
    def _resolve_full_heading_path(self, content: str, target_heading: str) -> str:
        """
        Resolve a partial heading to its full path as required by API v3.0+
        
        API v3.0+ requires full heading paths like: "Level1::Level2::Level3"
        """
        lines = content.split('\n')
        heading_stack = []
        target_level = target_heading.count('#')
        target_text = target_heading.lstrip('#').strip()
        
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                level = 0
                while level < len(line) and line[level] == '#':
                    level += 1
                
                heading_text = line[level:].strip()
                
                # Maintain heading stack for current context
                heading_stack = heading_stack[:level-1]  # Remove deeper levels
                heading_stack.append(heading_text)
                
                # Check if this is our target heading
                if level == target_level and heading_text == target_text:
                    # Return full path
                    return "::".join(heading_stack)
        
        # If not found, return original target
        return target_heading

    def delete_file(self, filepath: str) -> Any:
        """Delete a file or directory from the vault.
        
        Args:
            filepath: Path to the file to delete (relative to vault root)
            
        Returns:
            None on success
        """
        url = f"{self.get_base_url()}/vault/{filepath}"
        
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
    
    def get_periodic_note(self, period: str) -> Any:
        """Get current periodic note for the specified period.
        
        Args:
            period: The period type (daily, weekly, monthly, quarterly, yearly)
            
        Returns:
            Content of the periodic note
        """
        url = f"{self.get_base_url()}/periodic/{period}/"
        
        def call_fn():
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
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
