import logging
import nextcord
from nextcord.ext import commands
from utils.voice import voice_manager
from utils.player import player_state
from utils.queue import song_queue
from utils.embed_factory import EmbedFactory

class NavigationCommands(commands.Cog):
    """Commands for navigation control (skip, stop, leave)"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Reference to the shared processing states
        playback_cog = bot.get_cog("PlaybackCommands")
        self.processing_states = playback_cog.processing_states if playback_cog else {}
    
    async def is_processing(self, guild_id: int, interaction: nextcord.Interaction) -> bool:
        """Check if the guild is currently processing songs and notify user if so"""
        if self.processing_states.get(guild_id, False):
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "wait", 
                    "Still processing songs... Please try again in a moment.",
                    success=False,
                    user=interaction.user
                )
            )
            return True
        return False

    @nextcord.slash_command(
        name="skip",
        description="Skip songs in the queue"
    )
    async def skip(
        self,
        interaction: nextcord.Interaction,
        position: int = None
    ):
        """
        Skip to a specific song in the queue
        Parameters
        ----------
        position: Which song position to skip to (optional, skips one song if not specified)
        """
        await interaction.response.defer()

        if await self.is_processing(interaction.guild_id, interaction):
            return

        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "skip", 
                    "I'm not playing anything right now.",
                    success=False,
                    user=interaction.user
                )
            )
            return

        if not voice_client.is_playing() and not voice_client.is_paused():
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "skip", 
                    "Nothing to skip right now.",
                    success=False,
                    user=interaction.user
                )
            )
            return

        # Get current song info for feedback
        current_song = player_state.get_song(interaction.guild_id)
        current_title = current_song.get('title', 'the current song') if current_song else 'the current song'

        # If no position specified, skip current song
        if position is None:
            voice_client.stop()
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "skip", 
                    f"Skipped **{current_title}**",
                    user=interaction.user
                )
            )
            return

        # Get current queue length
        queue_length = song_queue.get_queue_length(interaction.guild_id)
        
        if queue_length == 0:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "skip", 
                    "The queue is empty!",
                    success=False,
                    user=interaction.user
                )
            )
            return
            
        if position < 1 or position > queue_length:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "skip", 
                    f"Invalid position. Please use a number between 1 and {queue_length}",
                    success=False,
                    user=interaction.user
                )
            )
            return

        # Get song info for the target position for better feedback
        target_song = song_queue.get_queue(interaction.guild_id)[position-1]
        target_title = target_song['song_info']['title'] if target_song else f"song at position {position}"

        # Stop current song
        voice_client.stop()
        
        # Remove songs before the requested position
        for _ in range(position - 1):
            song_queue.pop_song(interaction.guild_id)

        await interaction.followup.send(
            embed=EmbedFactory.create_action_embed(
                "skip", 
                f"Skipped to **{target_title}**",
                user=interaction.user
            )
        )

    @nextcord.slash_command(
        name="stop",
        description="Stop playing and clear the queue"
    )
    async def stop(self, interaction: nextcord.Interaction):
        """Stop playing and clear the queue but stay in voice channel"""
        await interaction.response.defer()

        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "stop", 
                    "I'm not connected to a voice channel.",
                    success=False,
                    user=interaction.user
                )
            )
            return

        # Get queue stats for better feedback
        queue_length = song_queue.get_queue_length(interaction.guild_id)
        current_song = player_state.get_song(interaction.guild_id)
        
        # Stop playback if playing
        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        
        # Clear the queue
        song_queue.clear_queue(interaction.guild_id)
        
        # Clear current song info
        player_state.clear_song(interaction.guild_id)
        
        # Customize message based on what was stopped
        details = "Stopped playback and cleared the queue"
        if current_song and queue_length > 0:
            details = f"Stopped **{current_song.get('title', 'current song')}** and cleared {queue_length} songs from the queue"
        elif current_song:
            details = f"Stopped **{current_song.get('title', 'current song')}**"
        elif queue_length > 0:
            details = f"Cleared {queue_length} songs from the queue"
            
        await interaction.followup.send(
            embed=EmbedFactory.create_action_embed(
                "stop", 
                details,
                user=interaction.user
            )
        )

    @nextcord.slash_command(
        name="leave",
        description="Leave the voice channel"
    )
    async def leave(self, interaction: nextcord.Interaction):
        """Stop playing, clear the queue, and leave the voice channel"""
        await interaction.response.defer()

        if not interaction.guild.voice_client:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "leave", 
                    "I'm not in a voice channel.",
                    success=False,
                    user=interaction.user
                )
            )
            return

        # Disconnect (this will handle stopping and clearing)
        await voice_manager.disconnect(interaction.guild_id)
        
        await interaction.followup.send(
            embed=EmbedFactory.create_action_embed(
                "leave", 
                "Stopped playback and left the voice channel",
                user=interaction.user
            )
        )

def setup(bot: commands.Bot) -> None:
    """Setup the NavigationCommands cog"""
    bot.add_cog(NavigationCommands(bot))