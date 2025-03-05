import time
import nextcord
import yt_dlp
import logging
import asyncio
import concurrent.futures
from typing import Optional, Dict, Any
from utils.cache_manager import youtube_cache, YTDL_CACHE

# Create a thread pool for CPU-bound operations
youtube_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="youtube_worker")

class PlayerState:
    """Manages the state of currently playing songs across guilds"""
    def __init__(self):
        self.current_songs: Dict[int, Dict[str, Any]] = {}
        self.voice_clients: Dict[int, nextcord.VoiceClient] = {}
        self.song_start_times: Dict[int, float] = {}
        self.pause_durations: Dict[int, float] = {}
        self.last_pause_time: Dict[int, float] = {}
        
        # YT-DLP configuration
        self.ytdl_format_options = {
            "format": "bestaudio/best",
            "noplaylist": False,
            "nocheckcertificate": True,
            "ignoreerrors": False,
            "logtostderr": False,
            "quiet": True,
            "no_warnings": True,
            "default_search": "auto",
            "source_address": "0.0.0.0",
            # Use the Docker cache path
            "cachedir": YTDL_CACHE,
            "extract_flat": False,
        }
        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        self.ytdl = yt_dlp.YoutubeDL(self.ytdl_format_options)

    def create_progress_bar(self, guild_id: int) -> Optional[str]:
        """Creates a stylized progress bar for the current song"""
        song_info = self.current_songs.get(guild_id)
        if not song_info:
            return None

        voice_client = self.voice_clients.get(guild_id)
        if not voice_client:
            return None

        # Calculate elapsed time with pause handling
        start_time = self.song_start_times.get(guild_id, time.time())
        pause_duration = self.pause_durations.get(guild_id, 0)
        
        # If currently paused, add the current pause duration
        if voice_client.is_paused() and guild_id in self.last_pause_time:
            pause_duration += time.time() - self.last_pause_time[guild_id]
            
        elapsed = time.time() - start_time - pause_duration
        duration = song_info['duration']
        is_paused = voice_client.is_paused()

        # Create progress bar
        bar_length = 15
        progress = min(elapsed / duration if duration > 0 else 0, 1.0)
        filled_length = int(bar_length * progress)
        
        # Get play/pause emoji based on state
        status_emoji = "⏸️" if is_paused else "▶️"
        
        # Build the progress bar with new style
        progress_bar = "▬" * filled_length + "🔘" + "▬" * (bar_length - filled_length)
        
        # Format timestamps with padding
        current_time = f"{int(elapsed) // 60:02d}:{int(elapsed) % 60:02d}"
        total_time = f"{int(duration) // 60:02d}:{int(duration) % 60:02d}"
        
        return f"{status_emoji} {progress_bar} `{current_time} / {total_time}`"

    async def extract_song_info(self, query: str) -> Dict[str, Any]:
        """Extract song information using YT-DLP with caching"""
        try:
            # Try to get from cache first
            try:
                return await youtube_cache.get_or_compute(self._extract_song_info_impl, query)
            except Exception as cache_error:
                logging.error(f"Error using cache, falling back to direct extraction: {cache_error}")
                return await self._extract_song_info_impl(query)
                
        except Exception as e:
            logging.error(f"Error extracting song info: {e}")
            raise

    async def _extract_song_info_impl(self, query: str) -> Dict[str, Any]:
        """Actual implementation of song info extraction using a thread pool"""
        try:
            # Run the blocking extract_info in a thread pool
            loop = asyncio.get_event_loop()
            start_time = time.time()
            
            # This runs in a separate thread to avoid blocking the event loop
            info = await loop.run_in_executor(
                youtube_executor, 
                lambda: self.ytdl.extract_info(query, download=False)
            )
            
            extraction_time = time.time() - start_time
            logging.info(f"YouTube extraction took {extraction_time:.2f}s for query: {query[:30]}...")
            
            if 'entries' in info:
                info = info['entries'][0]  # Get first item from playlist
                
            # Get the highest quality thumbnail available
            thumbnail = None
            if info.get('thumbnails'):
                thumbnails = sorted(
                    [t for t in info['thumbnails'] if t.get('width')],
                    key=lambda x: (x.get('width', 0) or 0),
                    reverse=True
                )
                if thumbnails:
                    thumbnail = thumbnails[0]['url']
            
            return {
                'url': info['url'],
                'title': info['title'],
                'duration': info.get('duration', 0),
                'thumbnail': thumbnail or info.get('thumbnail'),
                'webpage_url': info.get('webpage_url', query),
                'uploader': info.get('uploader', 'Unknown'),
                'extracted_at': time.time()  # Add timestamp for cache monitoring
            }
        except Exception as e:
            logging.error(f"Error in threaded YouTube extraction: {e}")
            raise

    def update_song(self, guild_id: int, song_info: Dict[str, Any], requester: nextcord.Member) -> None:
        """Update the currently playing song information"""
        self.current_songs[guild_id] = {
            'title': song_info['title'],
            'duration': song_info['duration'],
            'thumbnail': song_info['thumbnail'],
            'url': song_info['webpage_url'],
            'uploader': song_info['uploader'],
            'requester': requester
        }
        
        # Reset timing data
        self.song_start_times[guild_id] = time.time()
        self.pause_durations[guild_id] = 0
        self.last_pause_time.pop(guild_id, None)

    def handle_pause(self, guild_id: int) -> None:
        """Record pause time for accurate progress tracking"""
        self.last_pause_time[guild_id] = time.time()
        
    def handle_resume(self, guild_id: int) -> None:
        """Update pause duration when resuming playback"""
        if guild_id in self.last_pause_time:
            pause_time = self.last_pause_time.pop(guild_id)
            self.pause_durations[guild_id] = self.pause_durations.get(guild_id, 0) + (time.time() - pause_time)

    def clear_song(self, guild_id: int) -> None:
        """Clear the song information when playback stops"""
        self.current_songs.pop(guild_id, None)
        self.song_start_times.pop(guild_id, None)
        self.pause_durations.pop(guild_id, None)
        self.last_pause_time.pop(guild_id, None)

    def get_song(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get current song information for a guild"""
        return self.current_songs.get(guild_id)

    def update_voice_client(self, guild_id: int, voice_client: nextcord.VoiceClient) -> None:
        """Update the voice client for a guild"""
        self.voice_clients[guild_id] = voice_client

    def remove_voice_client(self, guild_id: int) -> None:
        """Remove the voice client for a guild"""
        self.voice_clients.pop(guild_id, None)

    async def create_player(self, song_info: Dict[str, Any]) -> nextcord.FFmpegOpusAudio:
        """Create an FFmpeg player for the song"""
        return await nextcord.FFmpegOpusAudio.from_probe(
            song_info['url'],
            **self.ffmpeg_options
        )
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get YouTube cache statistics"""
        return youtube_cache.get_stats()

# Global instance for use across the bot
player_state = PlayerState()

# Add a function to clean up the thread pool on shutdown
async def shutdown_player():
    """Shutdown the player's thread pool"""
    youtube_executor.shutdown(wait=True)
    logging.info("Shutdown YouTube thread pool")