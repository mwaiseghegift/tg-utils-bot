from urllib.parse import urlparse, unquote
import httpx
import time
from utils.constants import (
    PHOTO_TYPES, 
    VIDEO_TYPES, 
    AUDIO_TYPES
)
from utils.utils import logger

class FileUploadBot:
    def __init__(self):
        self.active_downloads = {}
        self.cancel_requests = set()  # Track cancel requests
    
    def create_progress_bar(self, percentage, length=20):
        """Create a visual progress bar"""
        filled = int(length * percentage / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"[{bar}] {percentage:.1f}%"
    
    def format_file_size(self, size_bytes):
        """Convert bytes to human readable format"""
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024.0 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f} {size_names[i]}"
    
    def extract_filename_from_url(self, url):
        """Extract filename from URL with better logic"""
        try:
            # Parse URL and get path
            parsed = urlparse(url)
            path = unquote(parsed.path)
            
            # Get filename from path
            filename = path.split('/')[-1]
            
            # If no filename in path, try to extract from query params
            if not filename or '.' not in filename:
                # Check common query parameters
                query_params = parsed.query
                for param in ['filename', 'file', 'name']:
                    if param in query_params:
                        filename = query_params.split(f'{param}=')[1].split('&')[0]
                        filename = unquote(filename)
                        break
            
            # If still no filename, generate one
            if not filename or '.' not in filename:
                filename = f"file_{int(time.time())}"
            
            return filename
        except Exception:
            return f"file_{int(time.time())}"
    
    def get_file_type(self, filename, content_type=None):
        """Determine file type for optimal Telegram upload"""
        ext = '.' + filename.lower().split('.')[-1] if '.' in filename else ''
        
        # Check by extension first
        if ext in PHOTO_TYPES:
            return 'photo'
        elif ext in VIDEO_TYPES:
            return 'video'
        elif ext in AUDIO_TYPES:
            return 'audio'
        
        # Check by content type if extension doesn't match
        if content_type:
            if content_type.startswith('image/'):
                return 'photo'
            elif content_type.startswith('video/'):
                return 'video'
            elif content_type.startswith('audio/'):
                return 'audio'
        
        return 'document'
    
    async def check_url_info(self, url):
        """Get file info without downloading the entire file"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.head(url, follow_redirects=True)
                if response.status_code != 200:
                    # If HEAD fails, try GET with range
                    response = await client.get(url, headers={'Range': 'bytes=0-1'})
                
                content_length = response.headers.get('content-length')
                content_type = response.headers.get('content-type', '')
                
                return {
                    'size': int(content_length) if content_length else None,
                    'content_type': content_type,
                    'url': str(response.url)  # Final URL after redirects
                }
        except Exception as e:
            logger.error(f"Error checking URL info: {e}")
            return None
