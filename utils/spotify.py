import os
import re
import logging
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import nextcord
from utils.cache_manager import spotify_cache, SPOTIFY_CACHE
from utils.embed_factory import EmbedFactory

class SpotifyManager:
    def __init__(self):
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
        self._spotify_client: Optional[spotipy.Spotify] = None
        
        # URL pattern matching
        self.url_patterns = {
            'track': r'spotify:track:|https?://[a-z]+\.spotify\.com/track/',
            'album': r'spotify:album:|https?://[a-z]+\.spotify\.com/album/',
            'playlist': r'spotify:playlist:|https?://[a-z]+\.spotify\.com/playlist/',
            'artist': r'spotify:artist:|https?://[a-z]+\.spotify\.com/artist/'
        }

    @property
    def spotify_client(self) -> spotipy.Spotify:
        """Lazy initialization of Spotify client"""
        if not self._spotify_client:
            if not (self.client_id and self.client_secret):
                raise ValueError("Spotify credentials not configured")
            
            try:
                # For client credentials flow, we don't need cache_path
                auth_manager = SpotifyClientCredentials(
                    client_id=self.client_id,
                    client_secret=self.client_secret
                )
                
                self._spotify_client = spotipy.Spotify(auth_manager=auth_manager)
                logging.info(f"Initialized Spotify client")
            except Exception as e:
                logging.error(f"Failed to initialize Spotify client: {e}")
                raise
                
        return self._spotify_client

    def is_spotify_url(self, url: str) -> bool:
        """Check if the URL is a Spotify URL"""
        return any(
            re.search(pattern, url)
            for pattern in self.url_patterns.values()
        )

    def get_url_type(self, url: str) -> Optional[str]:
        """Determine the type of Spotify URL"""
        for url_type, pattern in self.url_patterns.items():
            if re.search(pattern, url):
                return url_type
        return None

    def get_spotify_id(self, url: str) -> str:
        """Extract Spotify ID from URL"""
        parsed = urlparse(url)
        return parsed.path.split('/')[-1]

    async def get_songs_from_url(self, url: str) -> List[Dict[str, Any]]:
        """Get song information from various Spotify URL types with caching"""
        try:
            # Generate cache key from URL
            return await spotify_cache.get_or_compute(self._get_songs_from_url_impl, url)
        except Exception as e:
            logging.error(f"Error in get_songs_from_url with caching: {e}")
            # Fall back to direct implementation if caching fails
            return await self._get_songs_from_url_impl(url)

    async def _get_songs_from_url_impl(self, url: str) -> List[Dict[str, Any]]:
        """Implementation of fetching songs from Spotify URL"""
        url_type = self.get_url_type(url)
        if not url_type:
            raise ValueError("Invalid Spotify URL")

        spotify_id = self.get_spotify_id(url)
        songs = []

        if url_type == 'track':
            track = self.spotify_client.track(spotify_id)
            songs.append(self._format_track(track))

        elif url_type == 'album':
            album = self.spotify_client.album_tracks(spotify_id)
            for track in album['items']:
                track['album'] = self.spotify_client.album(spotify_id)
                songs.append(self._format_track(track))

        elif url_type == 'playlist':
            results = self.spotify_client.playlist_tracks(spotify_id)
            while results:
                for item in results['items']:
                    if item['track']:
                        songs.append(self._format_track(item['track']))
                if results['next']:
                    results = self.spotify_client.next(results)
                else:
                    break

        elif url_type == 'artist':
            top_tracks = self.spotify_client.artist_top_tracks(spotify_id)
            for track in top_tracks['tracks']:
                songs.append(self._format_track(track))

        return songs

    def _format_track(self, track: Dict[str, Any]) -> Dict[str, Any]:
        """Format track information for queue system"""
        artists = ", ".join(artist['name'] for artist in track['artists'])
        
        # Format search query for YouTube
        search_query = f"{track['name']} {artists} official audio"
        
        return {
            'title': f"{track['name']} - {artists}",
            'search_query': search_query,
            'duration': round(track['duration_ms'] / 1000),  # Convert to seconds
            'spotify_url': track['external_urls']['spotify'],
            'artists': artists,
            'album': track['album']['name'] if 'album' in track else None,
            'release_date': track['album']['release_date'] if 'album' in track else None,
            'thumbnail': track['album']['images'][0]['url'] if 'album' in track and track['album']['images'] else None
        }

    def create_spotify_embed(self, track_info: Dict[str, Any]) -> nextcord.Embed:
        """Create an embed for Spotify track information"""
        embed = EmbedFactory.create_basic_embed(
            title=track_info['title'],
            description=f"[Open on Spotify]({track_info['spotify_url']})",
            color=nextcord.Color.from_rgb(30, 215, 96),  # Spotify green
            thumbnail=track_info['thumbnail']
        )
            
        embed.add_field(name="Artists", value=track_info['artists'], inline=True)
        if track_info['album']:
            embed.add_field(name="Album", value=track_info['album'], inline=True)
        if track_info['release_date']:
            embed.add_field(name="Release Date", value=track_info['release_date'], inline=True)
            
        duration = f"{track_info['duration'] // 60}:{track_info['duration'] % 60:02d}"
        embed.add_field(name="Duration", value=duration, inline=True)
        
        embed.set_footer(text="Powered by Spotify", icon_url="https://i.imgur.com/q4qNzb9.png")
        
        return embed

    async def handle_spotify_url(self, interaction: nextcord.Interaction, url: str) -> bool:
        """
        Handle a Spotify URL and add songs to queue
        Returns True if successful, False otherwise
        """
        try:
            songs = await self.get_songs_from_url(url)
            if not songs:
                await interaction.followup.send(
                    embed=EmbedFactory.create_action_embed(
                        "spotify",
                        "No songs found in the Spotify link.",
                        success=False,
                        user=interaction.user
                    )
                )
                return False
                
            if len(songs) > 1:
                await interaction.followup.send(
                    embed=EmbedFactory.create_action_embed(
                        "spotify",
                        f"Adding {len(songs)} songs from Spotify to the queue...",
                        success=True,
                        user=interaction.user
                    )
                )
                
            return True
            
        except Exception as e:
            logging.error(f"Error handling Spotify URL: {e}")
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "error",
                    "An error occurred while processing the Spotify link. Please try again.",
                    success=False,
                    user=interaction.user
                )
            )
            return False

# Global instance for use across the bot
spotify_manager = SpotifyManager()