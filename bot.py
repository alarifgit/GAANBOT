import os
import logging
import nextcord
from nextcord.ext import commands
from utils.voice import voice_manager
from utils.cache_manager import start_cleanup_task, stop_cleanup_task
from utils.player import shutdown_player
import signal
import asyncio

# Load environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
BOT_ACTIVITY_TYPE = os.getenv("BOT_ACTIVITY_TYPE", "playing").lower()
BOT_ACTIVITY = os.getenv("BOT_ACTIVITY", "music with GAANBOT")

# Ensure Discord token is set
if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN environment variable is not set!")

# Configure bot intents
intents = nextcord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

# Initialize bot
bot = commands.Bot(intents=intents)

# Set bot activity based on environment variables
if BOT_ACTIVITY_TYPE == "playing":
    activity = nextcord.Game(name=BOT_ACTIVITY)
elif BOT_ACTIVITY_TYPE == "listening":
    activity = nextcord.Activity(type=nextcord.ActivityType.listening, name=BOT_ACTIVITY)
elif BOT_ACTIVITY_TYPE == "watching":
    activity = nextcord.Activity(type=nextcord.ActivityType.watching, name=BOT_ACTIVITY)
else:
    activity = nextcord.Game(name=BOT_ACTIVITY)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@bot.event
async def on_ready():
    """Handle bot startup"""
    logging.info(f"GAANBOT is online as {bot.user}!")
    
    # Generate invite URL with required permissions
    permissions = nextcord.Permissions(
        connect=True,
        speak=True,
        use_voice_activation=True,
        view_channel=True,
        send_messages=True,
        read_message_history=True,
    )
    
    invite_url = nextcord.utils.oauth_url(
        str(bot.user.id),
        permissions=permissions,
        scopes=['bot', 'applications.commands']
    )
    
    logging.info(f"Invite URL: {invite_url}")
    await bot.change_presence(activity=activity)
    await bot.sync_all_application_commands()
    
    # Start the cache cleanup task now that the bot is ready
    start_cleanup_task()

@bot.event
async def on_voice_state_update(member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState):
    """Handle voice state updates"""
    if member.guild.voice_client:
        # Get number of human users in the channel
        members = member.guild.voice_client.channel.members
        human_members = [m for m in members if not m.bot]
        
        # If no humans left in the channel
        if len(human_members) == 0:
            try:
                await voice_manager.disconnect(member.guild.id)
            except Exception as e:
                logging.error(f"Error disconnecting from voice: {e}")

def load_cogs():
    """Load all command cogs"""
    # Get the absolute path to the commands directory
    commands_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commands")
    
    if not os.path.exists(commands_dir):
        logging.error(f"Commands directory not found at {commands_dir}")
        return False
        
    try:
        # Load each command file
        for filename in os.listdir(commands_dir):
            if filename.endswith(".py"):
                try:
                    bot.load_extension(f"commands.{filename[:-3]}")
                    logging.info(f"Loaded extension: {filename[:-3]}")
                except Exception as e:
                    logging.error(f"Failed to load extension {filename}: {e}")
                    return False
        return True
    except Exception as e:
        logging.error(f"Error loading cogs: {e}")
        return False

# Add a function to handle graceful shutdown
def signal_handler(sig, frame):
    """Handle termination signals"""
    logging.info(f"Received signal {sig}, shutting down...")
    
    # Stop the cache cleanup task
    stop_cleanup_task()
    
    # Create a task to handle async shutdown operations
    if not asyncio.get_event_loop().is_closed():
        shutdown_task = asyncio.create_task(shutdown_bot())
        # Wait a short time for shutdown to complete
        try:
            asyncio.get_event_loop().run_until_complete(asyncio.wait_for(shutdown_task, timeout=5.0))
        except asyncio.TimeoutError:
            logging.warning("Shutdown timed out, forcing exit")

async def shutdown_bot():
    """Handle graceful bot shutdown"""
    logging.info("Performing graceful shutdown...")
    
    # Disconnect from all voice channels
    for guild in bot.guilds:
        if guild.voice_client:
            await guild.voice_client.disconnect()
    
    # Shutdown the thread pool
    await shutdown_player()
    
    # Close the bot
    await bot.close()
    
    logging.info("Shutdown complete")

if __name__ == "__main__":
    try:
        # Register signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Load command cogs
        if not load_cogs():
            logging.error("Failed to load one or more cogs!")
            exit(1)
            
        # Initialize voice manager
        if voice_manager is not None:
            voice_manager.setup(bot)
            logging.info("Voice manager initialized successfully")
        else:
            logging.error("Failed to initialize voice manager!")
            exit(1)
            
        # Run the bot
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        exit(1)
    finally:
        # Ensure cleanup happens
        stop_cleanup_task()
        if not asyncio.get_event_loop().is_closed():
            asyncio.get_event_loop().run_until_complete(shutdown_player())