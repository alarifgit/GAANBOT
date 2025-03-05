from typing import Dict, List, Optional, Any
import nextcord
from collections import defaultdict
import random

class QueueManager:
    def __init__(self):
        # Using defaultdict to automatically initialize empty lists for new guild IDs
        self.queues: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
        self.max_queue_size = 500  # Maximum songs per server queue

    def add_song(self, guild_id: int, song_info: Dict[str, Any], requester: nextcord.Member) -> bool:
        """
        Add a song to the guild's queue
        Returns True if successful, False if queue is full
        """
        if len(self.queues[guild_id]) >= self.max_queue_size:
            return False

        self.queues[guild_id].append({
            'song_info': song_info,
            'requester': requester
        })
        return True
    
    def update_song_metadata(self, guild_id: int, position: int, new_info: dict) -> bool:
        """Update a song's metadata in the queue"""
        try:
            if 0 <= position < len(self.queues[guild_id]):
                self.queues[guild_id][position]['song_info'].update({
                    'url': new_info['url'],
                    'webpage_url': new_info['webpage_url'],
                    'thumbnail': new_info.get('thumbnail'),
                    'uploader': new_info['uploader']
                })
                return True
            return False
        except Exception as e:
            logging.error(f"Error updating song metadata: {e}")
            return False

    def pop_song(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Remove and return the next song in the queue"""
        if not self.queues[guild_id]:
            return None
        return self.queues[guild_id].pop(0)

    def clear_queue(self, guild_id: int) -> None:
        """Clear the queue for a guild"""
        self.queues[guild_id].clear()

    def remove_song(self, guild_id: int, index: int) -> bool:
        """
        Remove a song at a specific index
        Returns True if successful, False if index is invalid
        """
        try:
            self.queues[guild_id].pop(index)
            return True
        except IndexError:
            return False

    def get_queue(self, guild_id: int) -> List[Dict[str, Any]]:
        """Get the current queue for a guild"""
        return self.queues[guild_id].copy()

    def get_queue_length(self, guild_id: int) -> int:
        """Get the number of songs in the queue"""
        return len(self.queues[guild_id])

    def move_song(self, guild_id: int, old_index: int, new_index: int) -> bool:
        """
        Move a song from one position to another
        Returns True if successful, False if either index is invalid
        """
        try:
            queue = self.queues[guild_id]
            if not (0 <= old_index < len(queue) and 0 <= new_index < len(queue)):
                return False
            
            song = queue.pop(old_index)
            queue.insert(new_index, song)
            return True
        except IndexError:
            return False

    def shuffle_queue(self, guild_id: int) -> None:
        """Shuffle the queue for a guild"""
        random.shuffle(self.queues[guild_id])

    def is_empty(self, guild_id: int) -> bool:
        """Check if the queue is empty"""
        return len(self.queues[guild_id]) == 0

    def get_queue_duration(self, guild_id: int) -> int:
        """Get the total duration of all songs in the queue in seconds"""
        return sum(song['song_info']['duration'] for song in self.queues[guild_id])

    def create_queue_embed(self, guild_id: int, page: int = 1, items_per_page: int = 10) -> nextcord.Embed:
        """Create an embed displaying the current queue"""
        queue = self.queues[guild_id]
        if not queue:
            return nextcord.Embed(
                title="Queue Empty",
                description="No songs in queue",
                color=nextcord.Color.gold()
            )

        # Calculate pagination
        total_pages = (len(queue) + items_per_page - 1) // items_per_page
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page

        # Create embed
        embed = nextcord.Embed(
            title="Current Queue",
            color=nextcord.Color.gold()
        )

        # Add queue items
        queue_list = []
        for idx, item in enumerate(queue[start_idx:end_idx], start=start_idx + 1):
            song_info = item['song_info']
            requester = item['requester']
            duration = f"{song_info['duration'] // 60}:{song_info['duration'] % 60:02d}"
            
            queue_list.append(
                f"`{idx}.` [{song_info['title']}]({song_info['webpage_url']}) | `{duration}`\n"
                f"┗ Requested by: {requester.mention}"
            )

        embed.description = "\n\n".join(queue_list)

        # Add queue information
        total_duration = self.get_queue_duration(guild_id)
        embed.add_field(
            name="Queue Info",
            value=f"Songs: {len(queue)} | Duration: {total_duration // 60}:{total_duration % 60:02d}",
            inline=False
        )

        # Add pagination information
        if total_pages > 1:
            embed.set_footer(text=f"Page {page}/{total_pages}")

        return embed

# Global instance for use across the bot
song_queue = QueueManager()