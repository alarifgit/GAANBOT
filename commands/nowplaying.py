import nextcord
from nextcord.ext import commands
from utils.player import player_state

class NowPlaying(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @nextcord.slash_command(
        name="now",
        description="Show information about the currently playing song"
    )
    async def now_playing(self, interaction: nextcord.Interaction):
        """Display information about the currently playing song"""
        await interaction.response.defer()

        # Get the music cog to check processing state
        music_cog = self.bot.get_cog("Music")
        if music_cog and music_cog.processing_queues.get(interaction.guild_id, False):
            await interaction.followup.send("Still processing songs... Please try again in a moment.")
            return

        # Get current song info
        song_info = player_state.get_song(interaction.guild_id)
        if not song_info:
            await interaction.followup.send("No song is currently playing.")
            return

        voice_client = interaction.guild.voice_client
        if not voice_client or (not voice_client.is_playing() and not voice_client.is_paused()):
            await interaction.followup.send("No song is currently playing.")
            return

        # Create progress bar
        progress_bar = player_state.create_progress_bar(interaction.guild_id)
        if not progress_bar:
            await interaction.followup.send("Error getting playback progress.")
            return

        # Create embed
        embed = nextcord.Embed(
            title="Now Playing",
            description=f"[{song_info['title']}]({song_info['url']})",
            color=nextcord.Color.blue()
        )

        # Set large image (appears below title)
        if song_info['thumbnail']:
            embed.set_image(url=song_info['thumbnail'])

        # Add progress bar below image
        embed.add_field(
            name="",
            value=progress_bar,
            inline=False
        )

        # Add song details in a row
        embed.add_field(
            name="Uploader",
            value=song_info['uploader'],
            inline=True
        )

        duration = song_info['duration']
        embed.add_field(
            name="Duration",
            value=f"{duration // 60}:{duration % 60:02d}",
            inline=True
        )

        status = "Paused" if voice_client.is_paused() else "Playing"
        embed.add_field(
            name="Status",
            value=status,
            inline=True
        )

        # Add requester info
        if song_info['requester']:
            embed.set_footer(
                text=f"Requested by {song_info['requester'].display_name}",
                icon_url=song_info['requester'].avatar.url if song_info['requester'].avatar else None
            )

        await interaction.followup.send(embed=embed)

def setup(bot: commands.Bot) -> None:
    """Setup the NowPlaying cog"""
    bot.add_cog(NowPlaying(bot))