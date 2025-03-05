import time
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple, List, TypeVar, Generic, Callable
import os

T = TypeVar('T')  # Generic type for cache values

# Define standard cache paths for Docker environment
CACHE_ROOT = "/app/cache"
YTDL_CACHE = os.path.join(CACHE_ROOT, "ytdl")
SPOTIFY_CACHE = os.path.join(CACHE_ROOT, "spotify")

class CacheEntry(Generic[T]):
    """Entry in the cache with value and expiration time"""
    def __init__(self, value: T, ttl: int):
        self.value = value
        self.expires_at = time.time() + ttl
    
    def is_expired(self) -> bool:
        """Check if the cache entry has expired"""
        return time.time() > self.expires_at


class AsyncLRUCache:
    """LRU cache for async functions"""
    def __init__(self, name: str, maxsize: int = 128, ttl: int = 3600):
        """
        Initialize the cache
        
        Parameters:
        -----------
        name: Name of this cache (for stats and logging)
        maxsize: Maximum number of entries in the cache
        ttl: Time to live in seconds (default: 1 hour)
        """
        self.name = name
        self.cache: Dict[str, CacheEntry] = {}
        self.maxsize = maxsize
        self.ttl = ttl
        self._lock = asyncio.Lock()
        
        # Add stats counters
        self.hits = 0
        self.misses = 0
        self.last_cleanup = 0
        
    def _generate_key(self, func_name: str, args: Tuple, kwargs: Dict[str, Any]) -> str:
        """Generate a unique key for the function call"""
        # Convert args and kwargs to a string representation
        args_str = ','.join(str(arg) for arg in args)
        kwargs_str = ','.join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return f"{func_name}:{args_str}:{kwargs_str}"
    
    async def get_or_compute(self, 
                            func: Callable,
                            *args,
                            **kwargs) -> Any:
        """
        Get a value from the cache or compute it if not present
        
        Parameters:
        -----------
        func: Async function to call if value not in cache
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
        Returns:
        --------
        The cached or computed value
        """
        cache_key = self._generate_key(func.__name__, args, kwargs)
        
        # Check if the key is in the cache and not expired
        entry = self.cache.get(cache_key)
        if entry and not entry.is_expired():
            logging.debug(f"Cache hit for {cache_key}")
            self.hits += 1
            return entry.value
        
        # If not in cache or expired, compute the value
        async with self._lock:
            # Double-check in case another coroutine has updated the cache
            entry = self.cache.get(cache_key)
            if entry and not entry.is_expired():
                self.hits += 1
                return entry.value
            
            # Compute the value
            try:
                logging.debug(f"Cache miss for {cache_key}, computing...")
                self.misses += 1
                result = await func(*args, **kwargs)
                
                # Update the cache
                self.cache[cache_key] = CacheEntry(result, self.ttl)
                
                # Trim the cache if it exceeds the max size
                if len(self.cache) > self.maxsize:
                    # Remove the oldest entries
                    oldest_keys = sorted(
                        self.cache.keys(),
                        key=lambda k: self.cache[k].expires_at
                    )[:len(self.cache) - self.maxsize]
                    
                    for key in oldest_keys:
                        del self.cache[key]
                
                return result
            except Exception as e:
                logging.error(f"Error computing value for cache: {e}")
                raise
    
    def invalidate(self, func_name: str, *args, **kwargs) -> None:
        """Invalidate a specific cache entry"""
        cache_key = self._generate_key(func_name, args, kwargs)
        if cache_key in self.cache:
            del self.cache[cache_key]
    
    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()
        
    async def cleanup_expired(self) -> None:
        """Remove all expired entries from the cache"""
        async with self._lock:
            expired_keys = [
                key for key, entry in self.cache.items() 
                if entry.is_expired()
            ]
            
            for key in expired_keys:
                del self.cache[key]
                
            if expired_keys:
                logging.info(f"Cleaned up {len(expired_keys)} expired entries from {self.name} cache")
                
            self.last_cleanup = time.time()
                
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = time.time()
        total_entries = len(self.cache)
        expired_entries = sum(1 for entry in self.cache.values() if entry.is_expired())
        active_entries = total_entries - expired_entries
        
        # Calculate hit ratio
        total_requests = self.hits + self.misses
        hit_ratio = self.hits / total_requests if total_requests > 0 else 0
        
        return {
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "active_entries": active_entries,
            "max_size": self.maxsize,
            "ttl": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio": hit_ratio,
            "last_cleanup": self.last_cleanup
        }

# Create cache directories
def ensure_cache_dirs():
    """Ensure all cache directories exist with proper permissions"""
    try:
        # Create main cache directory
        os.makedirs(CACHE_ROOT, exist_ok=True)
        
        # Create YouTube cache directory
        os.makedirs(YTDL_CACHE, exist_ok=True)
        
        # Create Spotify cache directory
        os.makedirs(SPOTIFY_CACHE, exist_ok=True)
        
        logging.info(f"Cache directories initialized at {CACHE_ROOT}")
    except Exception as e:
        logging.error(f"Error creating cache directories: {e}")

# Create global cache instances
youtube_cache = AsyncLRUCache(
    name="youtube",
    maxsize=100, 
    ttl=3600  # 1 hour TTL for YouTube data
)

spotify_cache = AsyncLRUCache(
    name="spotify",
    maxsize=50, 
    ttl=7200   # 2 hour TTL for Spotify data
)

image_cache = AsyncLRUCache(
    name="image",
    maxsize=200, 
    ttl=86400   # 24 hour TTL for images
)

# Cleanup task and its management
_cleanup_task = None

async def run_periodic_cleanup():
    """Run periodic cleanup of all caches"""
    while True:
        try:
            await asyncio.sleep(1800)  # Run every 30 minutes
            await youtube_cache.cleanup_expired()
            await spotify_cache.cleanup_expired()
            await image_cache.cleanup_expired()
        except asyncio.CancelledError:
            # Handle task cancellation gracefully
            logging.info("Cache cleanup task cancelled")
            break
        except Exception as e:
            logging.error(f"Error in cache cleanup: {e}")

def start_cleanup_task():
    """Start the cleanup task if it's not already running"""
    global _cleanup_task
    
    # Ensure cache directories exist first
    ensure_cache_dirs()
    
    if _cleanup_task is None or _cleanup_task.done():
        try:
            _cleanup_task = asyncio.create_task(run_periodic_cleanup())
            logging.info("Started cache cleanup background task")
        except RuntimeError:
            # Handle case where there's no event loop
            logging.info("No event loop available yet - will start cleanup task later")

def stop_cleanup_task():
    """Stop the cleanup task if it's running"""
    global _cleanup_task
    
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        logging.info("Cancelled cache cleanup background task")