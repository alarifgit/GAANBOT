import nextcord
import time
import psutil
import os
from datetime import datetime, timedelta
from nextcord.ext import commands
from utils.player import player_state
from utils.voice import voice_manager
from utils.cache_manager import youtube_cache, spotify_cache
from utils.embed_factory import EmbedFactory

class Statistics(commands.Cog):
    """Commands for viewing bot statistics and history"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    @nextcord.slash_command(
        name="stats",
        description="Show bot statistics and cache information"
    )
    async def stats(self, interaction: nextcord.Interaction):
        """Display bot statistics and cache information"""
        await interaction.response.defer()
        
        try:
            # Get YouTube cache stats
            yt_stats = youtube_cache.get_stats()
            
            # Get Spotify cache stats
            spotify_stats = spotify_cache.get_stats()
            
            # Create embed
            embed = EmbedFactory.create_basic_embed(
                title="GAANBOT Statistics",
                description="Current bot statistics and cache information",
                color=nextcord.Color.gold()
            )
            
            # Add bot stats
            guild_count = len(self.bot.guilds)
            
            # Count connected voice clients
            voice_count = 0
            for guild in self.bot.guilds:
                if guild.voice_client and guild.voice_client.is_connected():
                    voice_count += 1
            
            # Get memory usage
            process = psutil.Process(os.getpid())
            memory_usage = process.memory_info().rss / 1024 / 1024  # Convert to MB
            
            embed.add_field(
                name="Bot Status",
                value=f"🏠 **Servers:** {guild_count}\n"
                      f"🎵 **Active voice:** {voice_count}\n"
                      f"⏱️ **Uptime:** {self._get_uptime()}\n"
                      f"💾 **Memory:** {memory_usage:.1f} MB",
                inline=False
            )
            
            # Format YouTube cache stats
            hit_ratio = yt_stats.get('hit_ratio', 0) * 100
            embed.add_field(
                name="YouTube Cache",
                value=f"💾 **Entries:** {yt_stats.get('active_entries', 0)}\n"
                      f"🎯 **Hit rate:** {hit_ratio:.1f}%\n"
                      f"⚡ **Hits:** {yt_stats.get('hits', 0)}\n"
                      f"❓ **Misses:** {yt_stats.get('misses', 0)}",
                inline=True
            )
            
            # Format Spotify cache stats
            spotify_hit_ratio = spotify_stats.get('hit_ratio', 0) * 100
            embed.add_field(
                name="Spotify Cache",
                value=f"💾 **Entries:** {spotify_stats.get('active_entries', 0)}\n"
                      f"🎯 **Hit rate:** {spotify_hit_ratio:.1f}%\n"
                      f"⚡ **Hits:** {spotify_stats.get('hits', 0)}\n"
                      f"❓ **Misses:** {spotify_stats.get('misses', 0)}",
                inline=True
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "error",
                    f"Error fetching statistics: {str(e)}",
                    success=False,
                    user=interaction.user
                )
            )
    
    @nextcord.slash_command(
        name="history",
        description="Show recently played songs"
    )
    async def history(
        self,
        interaction: nextcord.Interaction,
        limit: int = 10
    ):
        """
        Display recently played songs
        Parameters
        ----------
        limit: Number of songs to show (default: 10, max: 20)
        """
        await interaction.response.defer()
        
        # Validate limit
        limit = min(max(1, limit), 20)
        
        try:
            # Get history from voice manager's recent songs tracker
            history = await voice_manager.get_recently_played(interaction.guild_id, limit)
            
            if not history:
                await interaction.followup.send(
                    embed=EmbedFactory.create_action_embed(
                        "history",
                        "No song history available for this server.",
                        success=False,
                        user=interaction.user
                    )
                )
                return
            
            # Create embed
            embed = EmbedFactory.create_basic_embed(
                title="Recently Played Songs",
                description=f"The last {len(history)} songs played in this server",
                color=nextcord.Color.purple()
            )
            
            # Add each song
            for i, song in enumerate(history, 1):
                duration = song.get('duration', 0)
                duration_str = f"{duration // 60}:{duration % 60:02d}" if duration else "?"
                
                requester_name = "Unknown"
                if song.get('requester'):
                    requester_name = song['requester'].display_name
                
                embed.add_field(
                    name=f"{i}. {song.get('title')}",
                    value=f"**Uploader:** {song.get('uploader', 'Unknown')}\n"
                          f"**Duration:** {duration_str}\n"
                          f"**Requested by:** {requester_name}",
                    inline=False
                )
            
            # Add thumbnail from most recent song
            if history[0].get('thumbnail'):
                embed.set_thumbnail(url=history[0].get('thumbnail'))
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "error",
                    f"Error fetching history: {str(e)}",
                    success=False,
                    user=interaction.user
                )
            )
    
    def _get_uptime(self) -> str:
        """Get bot uptime in a human-readable format"""
        uptime_seconds = time.time() - self.start_time
        
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{int(days)}d")
        if hours > 0 or days > 0:
            parts.append(f"{int(hours)}h")
        if minutes > 0 or hours > 0 or days > 0:
            parts.append(f"{int(minutes)}m")
        parts.append(f"{int(seconds)}s")
        
        return " ".join(parts)

def setup(bot: commands.Bot) -> None:
    """Setup the Statistics cog"""
    bot.add_cog(Statistics(bot))