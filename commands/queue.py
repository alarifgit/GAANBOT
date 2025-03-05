import nextcord
from nextcord.ext import commands
from utils.queue import song_queue

class Queue(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @nextcord.slash_command(
        name="queue",
        description="Show the current song queue"
    )
    async def view_queue(
        self,
        interaction: nextcord.Interaction,
        page: int = 1
    ):
        """
        Display the current queue
        Parameters
        ----------
        page: Which page of the queue to display
        """
        await interaction.response.defer()

        # Get the music cog to check processing state
        music_cog = self.bot.get_cog("Music")
        if music_cog and music_cog.processing_queues.get(interaction.guild_id, False):
            await interaction.followup.send("Still processing songs... Please try again in a moment.")
            return

        if song_queue.is_empty(interaction.guild_id):
            await interaction.followup.send("The queue is empty!")
            return

        # Create and send queue embed
        embed = song_queue.create_queue_embed(interaction.guild_id, page)
        await interaction.followup.send(embed=embed)

    @nextcord.slash_command(
        name="clear",
        description="Clear the song queue"
    )
    async def clear_queue(self, interaction: nextcord.Interaction):
        """Clear all songs from the queue"""
        await interaction.response.defer()

        if song_queue.is_empty(interaction.guild_id):
            await interaction.followup.send("The queue is already empty!")
            return

        song_queue.clear_queue(interaction.guild_id)
        await interaction.followup.send("🗑️ Cleared the queue!")

    @nextcord.slash_command(
        name="remove",
        description="Remove a song from the queue"
    )
    async def remove_song(
        self,
        interaction: nextcord.Interaction,
        position: int
    ):
        """
        Remove a song from the queue by its position
        Parameters
        ----------
        position: Position of the song in the queue (1-based)
        """
        await interaction.response.defer()

        # Convert to 0-based index
        index = position - 1
        
        if song_queue.remove_song(interaction.guild_id, index):
            await interaction.followup.send(f"Removed song at position {position} from the queue.")
        else:
            await interaction.followup.send(
                f"Invalid position. Please use a number between 1 and {song_queue.get_queue_length(interaction.guild_id)}"
            )

    @nextcord.slash_command(
        name="move",
        description="Move a song to a different position in the queue"
    )
    async def move_song(
        self,
        interaction: nextcord.Interaction,
        from_position: int,
        to_position: int
    ):
        """
        Move a song to a different position in the queue
        Parameters
        ----------
        from_position: Current position of the song (1-based)
        to_position: New position for the song (1-based)
        """
        await interaction.response.defer()

        # Convert to 0-based indices
        from_index = from_position - 1
        to_index = to_position - 1

        if song_queue.move_song(interaction.guild_id, from_index, to_index):
            await interaction.followup.send(
                f"Moved song from position {from_position} to {to_position}."
            )
        else:
            queue_length = song_queue.get_queue_length(interaction.guild_id)
            await interaction.followup.send(
                f"Invalid positions. Please use numbers between 1 and {queue_length}"
            )

    @nextcord.slash_command(
        name="shuffle",
        description="Shuffle the song queue"
    )
    async def shuffle_queue(self, interaction: nextcord.Interaction):
        """Randomly shuffle the queue"""
        await interaction.response.defer()

        # Get the music cog to check processing state
        music_cog = self.bot.get_cog("Music")
        if music_cog and music_cog.processing_queues.get(interaction.guild_id, False):
            await interaction.followup.send("Still processing songs... Please try again in a moment.")
            return

        if song_queue.is_empty(interaction.guild_id):
            await interaction.followup.send("The queue is empty!")
            return

        song_queue.shuffle_queue(interaction.guild_id)
        await interaction.followup.send("🔀 Shuffled the queue!")

def setup(bot: commands.Bot) -> None:
    """Setup the Queue cog"""
    bot.add_cog(Queue(bot))