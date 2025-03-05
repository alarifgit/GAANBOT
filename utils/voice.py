import asyncio
import logging
import time
import nextcord
from typing import Optional, Dict, Any, List
from .player import player_state
from .queue import song_queue
from .embed_factory import EmbedFactory

class VoiceManager:
    def __init__(self):
        self.bot: Optional[nextcord.Client] = None
        self._inactivity_timeouts: Dict[int, asyncio.Task] = {}
        self.command_channels: Dict[int, nextcord.TextChannel] = {}
        self.reconnect_attempts: Dict[int, int] = {}
        self.max_reconnect_attempts = 3  # Maximum reconnection attempts
        self.reconnect_backoff = 5  # Base seconds to wait between reconnection attempts
        self.reconnect_tasks: Dict[int, asyncio.Task] = {}
        
        # Store the last 5 played songs for resilience
        self.recent_songs: Dict[int, List[Dict[str, Any]]] = {}
        self.max_recent_songs = 5
        
        # Rate limiting protection
        self.last_api_call: Dict[str, float] = {}
        self.min_api_interval = 0.5  # Seconds between API calls

    def setup(self, bot: nextcord.Client) -> None:
        """Initialize the voice manager with the bot instance"""
        if not isinstance(bot, nextcord.Client):
            raise ValueError("Invalid bot instance provided")
        self.bot = bot
        
        # Register the voice state update event handler
        bot.add_listener(self.on_voice_state_update, 'on_voice_state_update')
        
        logging.info("VoiceManager setup completed")

    async def join_voice_channel(self, interaction: nextcord.Interaction) -> Optional[nextcord.VoiceClient]:
        """Join a voice channel and set up inactivity checker"""
        if not interaction.user.voice:
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "error",
                    "You need to be in a voice channel!",
                    success=False,
                    user=interaction.user
                )
            )
            return None

        try:
            # Rate limiting protection
            await self._respect_rate_limit('join_voice')
            
            # Connect to voice channel
            voice_client = await interaction.user.voice.channel.connect()
            player_state.update_voice_client(interaction.guild_id, voice_client)
            
            # Store the channel for reconnection purposes
            self.command_channels[interaction.guild_id] = interaction.channel
            
            # Reset reconnection counter on successful connection
            self.reconnect_attempts[interaction.guild_id] = 0
            
            # Start inactivity checker
            self._start_inactivity_checker(interaction.guild_id)
            
            return voice_client
        except Exception as e:
            logging.error(f"Error joining voice channel: {e}")
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "error",
                    "Failed to join voice channel. Please try again.",
                    success=False,
                    user=interaction.user
                )
            )
            return None

    async def _respect_rate_limit(self, action_key: str) -> None:
        """Ensure we don't exceed API rate limits"""
        now = time.time()
        last_call = self.last_api_call.get(action_key, 0)
        time_since_last = now - last_call
        
        if time_since_last < self.min_api_interval:
            # Wait to respect rate limit
            await asyncio.sleep(self.min_api_interval - time_since_last)
        
        # Update the last call time
        self.last_api_call[action_key] = time.time()

    def _start_inactivity_checker(self, guild_id: int) -> None:
        """Start checking for voice channel inactivity"""
        if guild_id in self._inactivity_timeouts:
            self._inactivity_timeouts[guild_id].cancel()
        
        self._inactivity_timeouts[guild_id] = asyncio.create_task(
            self._check_inactivity(guild_id)
        )

    async def _check_inactivity(self, guild_id: int) -> None:
        """Check for voice channel inactivity and disconnect if inactive"""
        try:
            while True:
                await asyncio.sleep(300)  # Check every 5 minutes
                voice_client = player_state.voice_clients.get(guild_id)
                
                if not voice_client or not voice_client.is_connected():
                    break
                    
                if not voice_client.is_playing() and not voice_client.is_paused():
                    # Get number of human users in the channel
                    members = voice_client.channel.members
                    human_members = [m for m in members if not m.bot]
                    
                    if len(human_members) == 0:
                        await self.disconnect(guild_id)
                        break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Error in inactivity checker: {e}")
        finally:
            self._inactivity_timeouts.pop(guild_id, None)

    async def on_voice_state_update(self, member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState):
        """Handle voice state updates for resilience"""
        # Skip if not the bot or the bot hasn't moved
        if member.id != self.bot.user.id:
            return
            
        guild_id = member.guild.id
        
        # Detect disconnection (bot was in a channel before but not after)
        if before.channel and not after.channel:
            logging.info(f"Bot disconnected from voice in guild {guild_id}")
            
            # If we still have a voice client and were playing, this might be an unexpected disconnect
            voice_client = player_state.voice_clients.get(guild_id)
            current_song = player_state.get_song(guild_id)
            
            if voice_client and (voice_client.is_playing() or voice_client.is_paused()) and current_song:
                logging.warning(f"Unexpected disconnect detected in guild {guild_id}")
                # Attempt to reconnect if we were playing music
                self._attempt_reconnection(guild_id, before.channel)
        
        # Handle guild change (moving to a different channel)
        elif before.channel and after.channel and before.channel.id != after.channel.id:
            logging.info(f"Bot moved to a different voice channel in guild {guild_id}")
            # Update the voice client reference in player_state
            voice_client = member.guild.voice_client
            if voice_client:
                player_state.update_voice_client(guild_id, voice_client)

    def _attempt_reconnection(self, guild_id: int, channel: nextcord.VoiceChannel) -> None:
        """Start a reconnection attempt task"""
        # Cancel any existing reconnection task
        if guild_id in self.reconnect_tasks and not self.reconnect_tasks[guild_id].done():
            self.reconnect_tasks[guild_id].cancel()
        
        # Create a new reconnection task
        self.reconnect_tasks[guild_id] = asyncio.create_task(
            self._reconnect_to_voice(guild_id, channel)
        )

    async def _reconnect_to_voice(self, guild_id: int, channel: nextcord.VoiceChannel) -> None:
        """Attempt to reconnect to voice channel with exponential backoff"""
        # Get the current attempts count or initialize to 0
        attempts = self.reconnect_attempts.get(guild_id, 0)
        
        # Store the current song and queue state before reconnecting
        current_song = player_state.get_song(guild_id)
        current_queue = song_queue.get_queue(guild_id)
        
        # Add current song to recent songs if available
        if current_song:
            if guild_id not in self.recent_songs:
                self.recent_songs[guild_id] = []
            self.recent_songs[guild_id].insert(0, current_song)
            # Trim to max size
            if len(self.recent_songs[guild_id]) > self.max_recent_songs:
                self.recent_songs[guild_id] = self.recent_songs[guild_id][:self.max_recent_songs]
        
        # Get the notification channel
        notification_channel = self.command_channels.get(guild_id)
        
        try:
            while attempts < self.max_reconnect_attempts:
                # Calculate backoff time with exponential increase
                backoff_time = self.reconnect_backoff * (2 ** attempts)
                logging.info(f"Attempting to reconnect to voice in guild {guild_id} in {backoff_time} seconds (attempt {attempts+1}/{self.max_reconnect_attempts})")
                
                # Wait before retrying
                await asyncio.sleep(backoff_time)
                
                # Attempt to reconnect
                try:
                    # Get the guild object
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        logging.error(f"Could not find guild {guild_id}")
                        break
                    
                    # Connect to the voice channel
                    voice_client = await channel.connect()
                    player_state.update_voice_client(guild_id, voice_client)
                    
                    # Notify about reconnection
                    if notification_channel:
                        await notification_channel.send(
                            embed=EmbedFactory.create_action_embed(
                                "connect",
                                "Reconnected to voice channel after connection issue",
                                success=True
                            )
                        )
                    
                    # Resume playback if we had a song playing
                    if current_song:
                        # Get the song info again
                        song_info = await player_state.extract_song_info(current_song['url'])
                        
                        # Create player
                        player = await player_state.create_player(song_info)
                        
                        # Play the song
                        voice_client.play(
                            player,
                            after=lambda e: asyncio.run_coroutine_threadsafe(
                                self._handle_song_end(guild_id, e is not None),
                                self.bot.loop
                            )
                        )
                        
                        # Restore the player state
                        player_state.update_song(
                            guild_id,
                            song_info,
                            current_song['requester']
                        )
                        
                        # Notify about resumed playback
                        if notification_channel:
                            await notification_channel.send(
                                embed=EmbedFactory.create_action_embed(
                                    "resume",
                                    f"Resumed playing **{current_song['title']}** after reconnection",
                                    success=True
                                )
                            )
                    
                    # Reset reconnection counter on successful connection
                    self.reconnect_attempts[guild_id] = 0
                    
                    # Start inactivity checker
                    self._start_inactivity_checker(guild_id)
                    
                    # Successfully reconnected
                    return
                    
                except Exception as e:
                    logging.error(f"Reconnection attempt {attempts+1} failed: {e}")
                    attempts += 1
                    self.reconnect_attempts[guild_id] = attempts
            
            # If we've exhausted all attempts, clean up
            if attempts >= self.max_reconnect_attempts:
                logging.warning(f"Failed to reconnect after {self.max_reconnect_attempts} attempts in guild {guild_id}")
                
                # Clean up resources
                player_state.clear_song(guild_id)
                player_state.remove_voice_client(guild_id)
                
                # Notify about failed reconnection
                if notification_channel:
                    await notification_channel.send(
                        embed=EmbedFactory.create_action_embed(
                            "error",
                            "Failed to reconnect to voice channel after multiple attempts. Please use `/play` to restart.",
                            success=False
                        )
                    )
                
        except asyncio.CancelledError:
            logging.info(f"Reconnection task cancelled for guild {guild_id}")
        except Exception as e:
            logging.error(f"Error in reconnection task: {e}")
        finally:
            # Clean up the task reference
            self.reconnect_tasks.pop(guild_id, None)

    async def play_song(self, interaction: nextcord.Interaction, query: str) -> None:
        """Play a song in a voice channel"""
        if not self.bot:
            logging.error("VoiceManager not properly initialized!")
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "error",
                    "An error occurred. Please try again later.",
                    success=False,
                    user=interaction.user
                )
            )
            return

        try:
            # Rate limiting protection
            await self._respect_rate_limit('extract_info')
            
            # Ensure bot is in voice channel
            voice_client = player_state.voice_clients.get(interaction.guild_id)
            if not voice_client or not voice_client.is_connected():
                voice_client = await self.join_voice_channel(interaction)
                if not voice_client:
                    return

            # Store the channel where the command was issued
            self.command_channels[interaction.guild_id] = interaction.channel

            # Extract song info
            song_info = await player_state.extract_song_info(query)
            
            # Create player
            player = await player_state.create_player(song_info)
            
            def after_playing(error: Optional[Exception]) -> None:
                if error:
                    logging.error(f"Error playing song: {error}")
                asyncio.run_coroutine_threadsafe(
                    self._handle_song_end(interaction.guild_id, error is not None),
                    self.bot.loop
                )

            # If already playing, add to queue
            if voice_client.is_playing() or voice_client.is_paused():
                position = song_queue.get_queue_length(interaction.guild_id) + 1
                song_queue.add_song(interaction.guild_id, song_info, interaction.user)
                
                # Create embed using the factory
                embed = EmbedFactory.create_song_embed(
                    song_info,
                    interaction.user,
                    is_now_playing=False,
                    position_in_queue=position
                )
                
                await interaction.followup.send(embed=embed)
                return

            # Play the song
            voice_client.play(player, after=after_playing)
            player_state.update_song(interaction.guild_id, song_info, interaction.user)
            
            # Create embed using the factory
            embed = EmbedFactory.create_song_embed(
                song_info,
                interaction.user,
                is_now_playing=True
            )
            
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logging.error(f"Error playing song: {e}")
            await interaction.followup.send(
                embed=EmbedFactory.create_action_embed(
                    "error",
                    "Failed to play the song. Please try again.",
                    success=False,
                    user=interaction.user
                )
            )

    async def _handle_song_end(self, guild_id: int, had_error: bool = False) -> None:
        """Handle song end and play next song if available"""
        if not self.bot:
            logging.error("VoiceManager not properly initialized!")
            return

        # Get the current song before clearing it
        current_song = player_state.get_song(guild_id)
        
        # Add current song to recent songs if available
        if current_song:
            if guild_id not in self.recent_songs:
                self.recent_songs[guild_id] = []
            self.recent_songs[guild_id].insert(0, current_song)
            # Trim to max size
            if len(self.recent_songs[guild_id]) > self.max_recent_songs:
                self.recent_songs[guild_id] = self.recent_songs[guild_id][:self.max_recent_songs]

        # Clear current song info
        player_state.clear_song(guild_id)
        
        # If error occurred, log and notify
        if had_error:
            logging.warning(f"Error occurred during playback in guild {guild_id}")
            channel = self.command_channels.get(guild_id)
            if channel:
                await channel.send(
                    embed=EmbedFactory.create_action_embed(
                        "error",
                        "An error occurred during playback. Attempting to continue with the next song.",
                        success=False
                    )
                )
        
        # Get next song from queue
        next_song = song_queue.pop_song(guild_id)
        if not next_song:
            return
            
        voice_client = player_state.voice_clients.get(guild_id)
        if not voice_client or not voice_client.is_connected():
            return

        try:
            # Rate limiting protection
            await self._respect_rate_limit('extract_info')
            
            song_info = next_song['song_info']
            
            # If this is a search query entry (from Spotify), get the YouTube info
            if song_info.get('search_query') and not song_info.get('url'):
                song_info = await player_state.extract_song_info(song_info['search_query'])

            # Create new player for next song
            player = await player_state.create_player(song_info)
            
            def after_playing(error: Optional[Exception]) -> None:
                if error:
                    logging.error(f"Error playing next song: {error}")
                asyncio.run_coroutine_threadsafe(
                    self._handle_song_end(guild_id, error is not None),
                    self.bot.loop
                )

            # Play the next song
            voice_client.play(player, after=after_playing)
            player_state.update_song(guild_id, song_info, next_song['requester'])
            
            # Create embed using the factory
            embed = EmbedFactory.create_song_embed(
                song_info,
                next_song['requester'],
                is_now_playing=True
            )

            # Send embed in the text channel
            # Use the stored channel where the /play command was issued
            channel = self.command_channels.get(guild_id)
            if channel:
                await channel.send(embed=embed)
            else:
                # Fallback to the system channel
                guild = next_song['requester'].guild
                channel = guild.system_channel
                if channel:
                    await channel.send(embed=embed)

        except Exception as e:
            logging.error(f"Error playing next song: {e}")
            # Try the next song in queue if available
            asyncio.create_task(self._handle_song_end(guild_id, True))

    async def disconnect(self, guild_id: int) -> None:
        """Disconnect from voice channel and clean up"""
        voice_client = player_state.voice_clients.get(guild_id)
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
        
        # Clean up
        player_state.clear_song(guild_id)
        player_state.remove_voice_client(guild_id)
        song_queue.clear_queue(guild_id)
        
        # Cancel inactivity checker
        if guild_id in self._inactivity_timeouts:
            self._inactivity_timeouts[guild_id].cancel()
            self._inactivity_timeouts.pop(guild_id)
            
        # Cancel any reconnection attempts
        if guild_id in self.reconnect_tasks and not self.reconnect_tasks[guild_id].done():
            self.reconnect_tasks[guild_id].cancel()
            self.reconnect_tasks.pop(guild_id)

    async def get_recently_played(self, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the recently played songs"""
        recent = self.recent_songs.get(guild_id, [])
        return recent[:min(limit, len(recent))]

# Create global instance
voice_manager = VoiceManager()