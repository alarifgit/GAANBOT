import nextcord
from typing import Optional, Dict, Any, List, Union

class EmbedFactory:
    """Factory for creating consistent embeds across the bot"""
    
    @staticmethod
    def create_basic_embed(
        title: str, 
        description: str = None, 
        color: nextcord.Color = nextcord.Color.blue(),
        footer_text: str = None,
        footer_icon: str = None,
        thumbnail: str = None
    ) -> nextcord.Embed:
        """Create a basic embed with consistent styling"""
        embed = nextcord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
            
        if footer_text:
            embed.set_footer(
                text=footer_text,
                icon_url=footer_icon
            )
            
        return embed
    
    @staticmethod
    def create_song_embed(
        song_info: Dict[str, Any],
        requester: nextcord.Member,
        is_now_playing: bool = False,
        position_in_queue: int = None
    ) -> nextcord.Embed:
        """Create a consistent song embed for now playing/queue add messages"""
        title = "Now Playing" if is_now_playing else "Added to Queue"
        color = nextcord.Color.blue() if is_now_playing else nextcord.Color.green()
        
        # Create description with position if provided
        description = f"[{song_info['title']}]({song_info['webpage_url']})"
        if position_in_queue is not None:
            description = f"#{position_in_queue} - {description}"
        
        embed = nextcord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        if song_info.get('thumbnail'):
            embed.set_thumbnail(url=song_info['thumbnail'])
            
        # Add song details
        embed.add_field(name="Uploader", value=song_info.get('uploader', 'Unknown'), inline=True)
        
        duration = song_info.get('duration', 0)
        embed.add_field(
            name="Duration",
            value=EmbedFactory.format_duration(duration),
            inline=True
        )
        
        # Add requester info
        embed.set_footer(
            text=f"Requested by {requester.display_name}",
            icon_url=requester.avatar.url if requester.avatar else None
        )
        
        return embed
    
    @staticmethod
    def create_action_embed(
        action: str,
        details: str = None,
        success: bool = True,
        user: nextcord.Member = None
    ) -> nextcord.Embed:
        """Create an embed for action responses (pause, skip, stop, etc.)"""
        # Pick emoji based on action and success
        emoji_map = {
            "pause": "⏸️",
            "resume": "▶️",
            "skip": "⏭️",
            "stop": "⏹️",
            "leave": "👋",
            "clear": "🗑️",
            "remove": "🗑️",
            "move": "↔️",
            "shuffle": "🔀",
            "wait": "⏳",
            "spotify": "🎵",
            "connect": "🔌",
            "error": "❌"
        }
        
        emoji = emoji_map.get(action.lower(), "🎵")
        if not success:
            emoji = emoji_map["error"]
        
        # Pick color based on success
        color = nextcord.Color.green() if success else nextcord.Color.red()
        
        # Create title with emoji
        title = f"{emoji} {action.capitalize()}"
        
        embed = nextcord.Embed(
            title=title,
            description=details,
            color=color
        )
        
        # Add user footer if provided
        if user:
            embed.set_footer(
                text=f"Requested by {user.display_name}",
                icon_url=user.avatar.url if user.avatar else None
            )
        
        return embed
    
    @staticmethod
    def format_duration(seconds: int) -> str:
        """Format seconds into MM:SS format"""
        return f"{seconds // 60}:{seconds % 60:02d}"