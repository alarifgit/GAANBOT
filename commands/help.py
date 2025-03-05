import nextcord
from nextcord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.command_categories = {
            "Music": [
                ("play", "Play a song from YouTube, Spotify, or a search query"),
                ("pause", "Pause the currently playing song"),
                ("resume", "Resume the paused song"),
                ("skip", "Skip the current song or skip to a specific position"),
                ("stop", "Stop playing and clear the queue (stays in voice channel)"),
                ("leave", "Stop playing, clear the queue, and leave the voice channel")
            ],
            "Queue": [
                ("queue", "Show the current song queue"),
                ("clear", "Clear the song queue"),
                ("remove", "Remove a song from the queue"),
                ("move", "Move a song to a different position"),
                ("shuffle", "Shuffle the song queue")
            ],
            "Now Playing": [
                ("now", "Show information about the currently playing song")
            ]
        }

    @nextcord.slash_command(
        name="help",
        description="Show all available commands"
    )
    async def help(self, interaction: nextcord.Interaction):
        """Display all available commands grouped by category"""
        await interaction.response.defer()
        
        # Check if songs are being processed
        music_cog = self.bot.get_cog("Music")
        is_processing = music_cog and music_cog.processing_queues.get(interaction.guild_id, False)
        
        embed = nextcord.Embed(
            title="GAANBOT Commands",
            description="Here are all available commands grouped by category:",
            color=nextcord.Color.blue()
        )

        # Add fields for each category
        for category, commands in self.command_categories.items():
            # Format commands for this category
            commands_text = "\n".join(
                f"`/{cmd}` - {desc}" for cmd, desc in commands
            )
            embed.add_field(
                name=category,
                value=commands_text,
                inline=False
            )
        
        # Add bot information and status
        footer_text = "Use / to access commands | GAANBOT created by chaosen3"
        if is_processing:
            footer_text = "⚠️ Processing songs... Some commands may be delayed | " + footer_text
            
        embed.set_footer(
            text=footer_text,
            icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None
        )

        await interaction.followup.send(embed=embed)

def setup(bot: commands.Bot) -> None:
    """Setup the Help cog"""
    bot.add_cog(Help(bot))