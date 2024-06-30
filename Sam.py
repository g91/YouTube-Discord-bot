import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio

# Initialize the bot with a command prefix and intents
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

# Configure yt-dlp options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,  # Allow playlist downloads
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'  # bind to ipv4 since ipv6 addresses cause issues sometimes
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')
        self.id = data.get('id')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # This is a playlist
            entries = data['entries']
            sources = []
            for entry in entries:
                filename = entry['url'] if stream else ytdl.prepare_filename(entry)
                sources.append(cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=entry))
            return sources
        else:
            # This is a single video
            filename = data['url'] if stream else ytdl.prepare_filename(data)
            return [cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)]

async def play_next(ctx):
    if ctx.voice_client.queue:
        next_song = ctx.voice_client.queue.pop(0)
        ctx.voice_client.current_song = next_song
        ctx.voice_client.play(next_song, after=lambda e: bot.loop.call_soon_threadsafe(asyncio.create_task, play_next(ctx)))
        await ctx.send(f'Now playing: {next_song.title} (ID: {next_song.id})')
    else:
        await ctx.send('Queue is empty.')

@bot.command()
async def play(ctx, url):
    # Find the Mansion channel
    channel = discord.utils.get(ctx.guild.voice_channels, name='Mansion')
    if not channel:
        await ctx.send("The channel 'Mansion' does not exist.")
        return

    # Connect to the channel
    try:
        if ctx.voice_client is not None:
            if ctx.voice_client.channel != channel:
                await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send(f"Joined {channel.name} voice channel.")
    except Exception as e:
        await ctx.send(f"Failed to join the voice channel: {e}")
        return

    # Download the YouTube video or playlist as an MP3
    try:
        async with ctx.typing():
            players = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
            if not hasattr(ctx.voice_client, 'queue'):
                ctx.voice_client.queue = []
            ctx.voice_client.queue.extend(players)
            for player in players:
                await ctx.send(f"Added to queue: {player.title} (ID: {player.id})")
    except Exception as e:
        await ctx.send(f"Failed to download and convert the video: {e}")
        return

    # Play the next song if not already playing
    if not ctx.voice_client.is_playing():
        await play_next(ctx)

@bot.command()
async def skip(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()

@bot.command()
async def skipto(ctx, song_id):
    if not hasattr(ctx.voice_client, 'queue'):
        await ctx.send("Queue is empty.")
        return

    song_to_play = None
    for index, song in enumerate(ctx.voice_client.queue):
        if song.id == song_id:
            song_to_play = ctx.voice_client.queue.pop(index)
            break

    if song_to_play:
        ctx.voice_client.queue.insert(0, song_to_play)
        ctx.voice_client.stop()
        await ctx.send(f"Skipped to: {song_to_play.title} (ID: {song_to_play.id})")
    else:
        await ctx.send(f"Song with ID {song_id} not found in the queue.")

@bot.command()
async def list(ctx):
    if not hasattr(ctx.voice_client, 'queue') or not ctx.voice_client.queue:
        await ctx.send("The queue is empty.")
        return

    queue_list = [f"{index+1}. {song.title} (ID: {song.id})" for index, song in enumerate(ctx.voice_client.queue)]
    queue_message = "\n".join(queue_list)
    await ctx.send(f"Current queue:\n{queue_message}")

@bot.command()
async def leave(ctx):
    if ctx.voice_client is not None:
        await ctx.voice_client.disconnect()
        await ctx.send("Disconnected from the voice channel.")

# Run the bot with your token
bot.run('')
