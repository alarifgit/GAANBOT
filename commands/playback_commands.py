import logging
import asyncio
import nextcord
from nextcord.ext import commands
from utils.voice import voice_manager
from utils.spotify import spotify_manager
from utils.player import player_state
from utils.queue import song_queue
from utils.embed_factory import EmbedFactory

class PlaybackCommands(commands.Cog):
    """Commands for basic playback control (play, pause, resume)"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.processing_states = {}  # Shared state for processing flags
    
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
        
    async def _process_spotify_songs(self, guild_id: int, songs: list, user, batch_size: int = 1):
        """Process Spotify songs in the background with proper yielding"""
        try:
            # Process songs in very small batches (1-2 songs at a time)
            for i in range(0, len(songs), batch_size):
                try:
                    # Get a batch of songs
                    batch = songs[i:i + batch_size]
                
                    # Process each song
                    for song in batch:
                        try:
                            # Let other tasks run between songs
                            await asyncio.sleep(0)
                        
                            # Extract song info (this is the blocking operation)
                            song_info = await player_state.extract_song_info(song['search_query'])
                        
                            # Add to queue
                            song_queue.add_song(guild_id, song_info, user)
                        except Exception as e:
                            logging.error(f"Error adding song to queue: {e}")
                
                    # Add a larger delay between batches to let voice heartbeats process
                    if i + batch_size < len(songs):
                        # Give more time for heartbeats
                        await asyncio.sleep(2)
                except Exception as batch_error:
                    logging.error(f"Error processing batch: {batch_error}")
                    continue
                
        except Exception as e:
            logging.error(f"Error in background processing: {e}")
        finally:
            # Clear processing state when done
            self.processing_states[guild_id] = False
            logging.info(f"Finished processing {len(songs)} Spotify songs for guild {guild_id}")

    @nextcord.slash_command(
        name="play",
        description="Play a song from YouTube, Spotify, or a search query"
    )
    async def play(
        self,
        interaction: nextcord.Interaction,
        query: str
    ):
        """Play a song or add it to the queue"""
        await interaction.response.defer()

        try:
            # Check if user is in voice channel
            if not interaction.user.voice:
                await interaction.followup.send(
                    embed=EmbedFactory.create_action_embed(
                        "error", 
                        "You need to be in a voice channel!",
                        success=False,
                        user=interaction.user
                    )
                )
                return

            # Handle Spotify URLs
            if spotify_manager.is_spotify_url(query):
                logging.info(f"Handling Spotify URL: {query}")
                try:
                    # Set processing state
                    self.processing_states[interaction.guild_id] = True
        
                    songs = await spotify_manager.get_songs_from_url(query)
                    if not songs:
                        self.processing_states[interaction.guild_id] = False
                        await interaction.followup.send(
                            embed=EmbedFactory.create_action_embed(
                                "spotify",
                                "No songs found in the Spotify link.",
                                success=False,
                                user=interaction.user
                            )
                        )
                        return

                    # Send acknowledgment for playlists/albums
                    if len(songs) > 1:
                        await interaction.followup.send(
                            embed=EmbedFactory.create_action_embed(
                                "spotify",
                                f"Adding {len(songs)} songs from Spotify to the queue...",
                                success=True,
                                user=interaction.user
                            )
                        )

                    # Get YouTube info for first song and play it
                    first_song = songs.pop(0)
                    await voice_manager.play_song(interaction, first_song['search_query'])

                    # Process remaining songs in smaller batches with yielding
                    voice_client = interaction.guild.voice_client
                    if voice_client and songs:
                        # Use a much smaller batch size (1-2 songs max per batch)
                        batch_size = 1
            
                        # Create a background task to process the songs
                        asyncio.create_task(self._process_spotify_songs(
                            interaction.guild_id, 
                            songs, 
                            interaction.user,
                            batch_size
                        ))
        
                    # Clear processing state is done in the background task
                    return
                except Exception as e:
                    # Clear processing state on error
                    self.processing_states[interaction.guild_id] = False
                    logging.error(f"Error processing Spotify URL: {e}", exc_info=True)
                    await interaction.followup.send(
                        embed=EmbedFactory.create_action_embed(
                            "error",
                            "An error occurred while processing the Spotify link. Please try again.",
                            success=False,
                            user=interaction.user
                        )
                    )
                    return

            # Handle regular URLs or search queries
            await voice_manager.play_song(interaction, query)

        except Exception as e:
            if interaction.guild_id in self.processing_states:
                self.processing_states[interaction.guild_id] = False
            logging.error(f"Error in play command: {e}")
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "error", 
                    "An error occurred while trying to play the song. Please try again.",
                    success=False,
                    user=interaction.user
                )
            )

    @nextcord.slash_command(
        name="pause",
        description="Pause the currently playing song"
    )
    async def pause(self, interaction: nextcord.Interaction):
        """Pause the current song"""
        await interaction.response.defer()

        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "pause", 
                    "I'm not playing anything right now.",
                    success=False,
                    user=interaction.user
                )
            )
            return

        if voice_client.is_paused():
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "pause", 
                    "The song is already paused!",
                    success=False,
                    user=interaction.user
                )
            )
            return

        if voice_client.is_playing():
            voice_client.pause()
            song_info = player_state.get_song(interaction.guild_id)
            
            if song_info:
                title = song_info.get('title', 'current song')
                await interaction.followup.send(
                    embed=EmbedFactory.create_action_embed(
                        "pause", 
                        f"Paused **{title}**",
                        user=interaction.user
                    )
                )
            else:
                await interaction.followup.send(
                    embed=EmbedFactory.create_action_embed(
                        "pause", 
                        "Paused the current song",
                        user=interaction.user
                    )
                )
            return

        await interaction.followup.send(
            embed=EmbedFactory.create_action_embed(
                "pause", 
                "Nothing is playing right now.",
                success=False,
                user=interaction.user
            )
        )

    @nextcord.slash_command(
        name="resume",
        description="Resume the paused song"
    )
    async def resume(self, interaction: nextcord.Interaction):
        """Resume the paused song"""
        await interaction.response.defer()

        voice_client = interaction.guild.voice_client
        if not voice_client:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "resume", 
                    "I'm not connected to a voice channel.",
                    success=False,
                    user=interaction.user
                )
            )
            return

        if voice_client.is_playing():
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "resume", 
                    "The song is already playing!",
                    success=False,
                    user=interaction.user
                )
            )
            return

        if voice_client.is_paused():
            voice_client.resume()
            song_info = player_state.get_song(interaction.guild_id)
            
            if song_info:
                title = song_info.get('title', 'current song')
                await interaction.followup.send(
                    embed=EmbedFactory.create_action_embed(
                        "resume", 
                        f"Resumed **{title}**",
                        user=interaction.user
                    )
                )
            else:
                await interaction.followup.send(
                    embed=EmbedFactory.create_action_embed(
                        "resume", 
                        "Resumed the song",
                        user=interaction.user
                    )
                )
            return

        await interaction.followup.send(
            embed=EmbedFactory.create_action_embed(
                "resume", 
                "Nothing is paused right now.",
                success=False,
                user=interaction.user
            )
        )

def setup(bot: commands.Bot) -> None:
    """Setup the PlaybackCommands cog"""
    bot.add_cog(PlaybackCommands(bot))