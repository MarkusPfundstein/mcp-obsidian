import requests
import urllib.parse
import os
import base64
import tempfile
import logging
from typing import Any

logger = logging.getLogger("mcp-obsidian")

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

        # Handle SSL certificate configuration
        self.temp_cert_file = None
        cert_base64 = os.getenv("OBSIDIAN_SSL_CERT_BASE64")
        cert_path = os.getenv("OBSIDIAN_SSL_CERT_PATH")

        logger.debug(f"SSL cert config: base64={'set' if cert_base64 else 'not set'}, path={cert_path}")

        if cert_base64:
            # Decode base64 certificate and write to temporary file
            logger.debug("Using base64-encoded certificate")
            try:
                cert_data = base64.b64decode(cert_base64)
                # Create a temporary file that persists
                temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pem')
                temp_file.write(cert_data)
                temp_file.close()
                self.temp_cert_file = temp_file.name
                self.verify_ssl = temp_file.name
                logger.debug(f"Base64 cert decoded and written to: {self.temp_cert_file}")
            except Exception as e:
                logger.error(f"Failed to decode OBSIDIAN_SSL_CERT_BASE64: {str(e)}", exc_info=True)
                raise ValueError(f"Failed to decode OBSIDIAN_SSL_CERT_BASE64: {str(e)}")
        elif cert_path:
            # Validate certificate file exists
            logger.debug(f"Using certificate file path: {cert_path}")
            if os.path.exists(cert_path):
                self.verify_ssl = cert_path
                logger.debug(f"Certificate file found and will be used for SSL verification")
            else:
                logger.error(f"SSL certificate file not found: {cert_path}")
                raise FileNotFoundError(f"SSL certificate file not found: {cert_path}")
        else:
            # No certificate provided, use default behavior
            self.verify_ssl = verify_ssl
            logger.debug(f"No SSL certificate configured, verify_ssl={verify_ssl}")

        self.timeout = (3, 6)

    def __del__(self):
        """Clean up temporary certificate file if it exists."""
        if self.temp_cert_file and os.path.exists(self.temp_cert_file):
            try:
                os.unlink(self.temp_cert_file)
            except Exception:
                # Silently ignore cleanup errors
                pass

    def get_base_url(self) -> str:
        return f'{self.protocol}://{self.host}:{self.port}'
    
    def _get_headers(self) -> dict:
        headers = {
            'Authorization': f'Bearer {self.api_key}'
        }
        return headers

    def _safe_call(self, f) -> Any:
        try:
            result = f()
            logger.debug(f"API request successful")
            return result
        except requests.HTTPError as e:
            error_data = e.response.json() if e.response.content else {}
            code = error_data.get('errorCode', -1)
            message = error_data.get('message', '<unknown>')
            logger.error(f"HTTP Error {code}: {message}, status_code={e.response.status_code}")
            raise Exception(f"Error {code}: {message}")
        except requests.exceptions.SSLError as e:
            logger.error(f"SSL Error: {str(e)}", exc_info=True)
            raise Exception(f"SSL Error: {str(e)}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed: {str(e)}", exc_info=True)
            raise Exception(f"Request failed: {str(e)}")

    def list_files_in_vault(self) -> Any:
        url = f"{self.get_base_url()}/vault/"

        def call_fn():
            logger.debug(f"GET {url} (verify_ssl={self.verify_ssl})")
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()

            return response.json()['files']

        return self._safe_call(call_fn)

        
    def list_files_in_dir(self, dirpath: str) -> Any:
        url = f"{self.get_base_url()}/vault/{dirpath}/"

        def call_fn():
            logger.debug(f"GET {url} (verify_ssl={self.verify_ssl})")
            response = requests.get(url, headers=self._get_headers(), verify=self.verify_ssl, timeout=self.timeout)
            response.raise_for_status()

            return response.json()['files']

        return self._safe_call(call_fn)

    def get_file_contents(self, filepath: str) -> Any:
        url = f"{self.get_base_url()}/vault/{filepath}"

        def call_fn():
            logger.debug(f"GET {url} (verify_ssl={self.verify_ssl})")
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
        url = f"{self.get_base_url()}/vault/{filepath}"
        
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
