import discord
from discord.ext import commands
import yt_dlp
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='-', intents=intents, help_command=None)  # Disable default help

YDL_OPTIONS = {
    'format': 'bestaudio',
    'noplaylist': True,
    'quiet': True
}
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

queues = {}  # Queue per guild
loop_flags = {}  # Loop toggle per guild

# Play next song in queue
async def play_next(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        url = queues[guild_id][0]
        ctx.voice_client.stop()
        ctx.voice_client.play(
            discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS),
            after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
        )
        if not loop_flags.get(guild_id, False):
            queues[guild_id].pop(0)

# ===== COMMANDS =====
@bot.command()
async def play(ctx, *, query: str = None):
    if query is None:
        await ctx.send("❌ You must provide a YouTube link or search term.")
        return

    if not ctx.author.voice:
        await ctx.send("❌ You must be in a voice channel to play music.")
        return

    voice_channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await voice_channel.connect()
    elif ctx.voice_client.channel != voice_channel:
        await ctx.voice_client.move_to(voice_channel)

    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            if "youtube.com" not in query and "youtu.be" not in query:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)
                url2 = info['entries'][0]['url']
                title = info['entries'][0]['title']
            else:
                info = ydl.extract_info(query, download=False)
                url2 = info['url']
                title = info.get('title', 'Unknown title')
    except Exception as e:
        await ctx.send(f"❌ Could not find/play: {e}")
        return

    guild_id = ctx.guild.id
    if guild_id not in queues:
        queues[guild_id] = []

    if ctx.voice_client.is_playing():
        queues[guild_id].append(url2)
        await ctx.send(f"⏱ Added to queue: {title}")
    else:
        queues[guild_id].append(url2)
        await play_next(ctx)
        await ctx.send(f"▶️ Now playing: {title}")

@bot.command()
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸ Music paused.")
    else:
        await ctx.send("❌ Nothing is playing right now.")

@bot.command()
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Music resumed.")
    else:
        await ctx.send("❌ Music is not paused.")

@bot.command()
async def stop(ctx):
    guild_id = ctx.guild.id
    if ctx.voice_client:
        ctx.voice_client.stop()
        queues[guild_id] = []
        await ctx.send("⏹ Music stopped and queue cleared.")
    else:
        await ctx.send("❌ Nothing is playing right now.")

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭ Skipped the current song.")
    else:
        await ctx.send("❌ Nothing is playing right now.")

@bot.command()
async def queue(ctx):
    guild_id = ctx.guild.id
    if guild_id in queues and queues[guild_id]:
        q = "\n".join([f"{i+1}. {song}" for i, song in enumerate(queues[guild_id])])
        await ctx.send(f"🎵 Queue:\n{q}")
    else:
        await ctx.send("❌ Queue is empty.")

@bot.command()
async def loop(ctx):
    guild_id = ctx.guild.id
    loop_flags[guild_id] = not loop_flags.get(guild_id, False)
    state = "enabled" if loop_flags[guild_id] else "disabled"
    await ctx.send(f"🔁 Loop is now **{state}**.")

@bot.command()
async def help(ctx):
    embed = discord.Embed(title="Music Bot Commands", color=discord.Color.blue())
    embed.add_field(name="-play <url/query>", value="Play a song or add to queue", inline=False)
    embed.add_field(name="-pause", value="Pause the current song", inline=False)
    embed.add_field(name="-resume", value="Resume paused music", inline=False)
    embed.add_field(name="-stop", value="Stop music and clear queue", inline=False)
    embed.add_field(name="-skip", value="Skip the current song", inline=False)
    embed.add_field(name="-queue", value="Show current queue", inline=False)
    embed.add_field(name="-loop", value="Toggle looping the current song/queue", inline=False)
    await ctx.send(embed=embed)

bot.run("DISCORD_TOKEN")



