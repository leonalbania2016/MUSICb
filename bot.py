import os
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import threading
from flask import Flask

# ===== KEEP ALIVE (Render Web Service support) =====
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", "10000") or "10000")
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

# ===== DISCORD SETUP =====
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='-', intents=intents)

# ===== GLOBALS =====
queues = {}
looping = {}

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'cookiefile': 'cookies.txt',  # Put your exported YouTube cookies here
    'noplaylist': True,
    'ignoreerrors': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

# ===== HELPER FUNCTIONS =====
def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]

async def play_next(ctx):
    queue = get_queue(ctx.guild.id)
    if len(queue) > 0:
        query = queue.pop(0)
        await play_song(ctx, query)
    else:
        voice = ctx.voice_client
        if voice:
            await voice.disconnect()

async def play_song(ctx, query):
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            url = info['url']
            title = info.get('title', 'Unknown Title')
    except Exception as e:
        await ctx.send(f"❌ Could not find/play: {e}")
        return

    voice_client = ctx.voice_client
    if voice_client is None:
        voice_channel = ctx.author.voice.channel
        voice_client = await voice_channel.connect()
    elif voice_client.channel != ctx.author.voice.channel:
        await voice_client.move_to(ctx.author.voice.channel)

    source = await discord.FFmpegOpusAudio.from_probe(url, **FFMPEG_OPTIONS)
    voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(after_song(ctx), bot.loop))
    await ctx.send(f"🎶 Now playing: **{title}**")

async def after_song(ctx):
    guild_id = ctx.guild.id
    if looping.get(guild_id):
        queue = get_queue(guild_id)
        if ctx.voice_client and ctx.voice_client.source:
            queue.insert(0, ctx.voice_client.source)
    await play_next(ctx)

# ===== COMMANDS =====
@bot.command(name='p')
async def play(ctx, *, query):
    """Play a song"""
    queue = get_queue(ctx.guild.id)
    queue.append(query)
    voice_client = ctx.voice_client

    if not voice_client or not voice_client.is_playing():
        await play_next(ctx)
    else:
        await ctx.send(f"✅ Added to queue: **{query}**")

@bot.command()
async def skip(ctx):
    """Skip the current song"""
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.stop()
        await ctx.send("⏭️ Skipped the current song.")
    else:
        await ctx.send("⚠️ Nothing is playing.")

@bot.command()
async def stop(ctx):
    """Stop playback and clear queue"""
    queue = get_queue(ctx.guild.id)
    queue.clear()
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.stop()
    await ctx.send("🛑 Stopped playback and cleared the queue.")

@bot.command()
async def pause(ctx):
    """Pause playback"""
    voice = ctx.voice_client
    if voice and voice.is_playing():
        voice.pause()
        await ctx.send("⏸️ Paused.")
    else:
        await ctx.send("⚠️ Nothing is playing.")

@bot.command()
async def resume(ctx):
    """Resume playback"""
    voice = ctx.voice_client
    if voice and voice.is_paused():
        voice.resume()
        await ctx.send("▶️ Resumed.")
    else:
        await ctx.send("⚠️ Nothing to resume.")

@bot.command()
async def queue(ctx):
    """Show queue"""
    q = get_queue(ctx.guild.id)
    if not q:
        await ctx.send("📭 Queue is empty.")
    else:
        queue_list = "\n".join([f"{i+1}. {song}" for i, song in enumerate(q)])
        await ctx.send(f"🎵 **Queue:**\n{queue_list}")

@bot.command()
async def loop(ctx):
    """Toggle loop mode"""
    guild_id = ctx.guild.id
    looping[guild_id] = not looping.get(guild_id, False)
    await ctx.send(f"🔁 Loop mode is now {'ON' if looping[guild_id] else 'OFF'}.")

@bot.command()
async def leave(ctx):
    """Leave voice channel"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel.")
    else:
        await ctx.send("⚠️ Not connected to any voice channel.")

@bot.command()
async def clear(ctx):
    """Clear the queue"""
    q = get_queue(ctx.guild.id)
    q.clear()
    await ctx.send("🧹 Cleared the queue.")

@bot.command()
async def ping(ctx):
    """Ping latency"""
    await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

@bot.command()
async def help(ctx):
    """Show all commands"""
    embed = discord.Embed(
        title="🎵 Lara Music Bot Commands",
        description="Use `-<command>` to control music",
        color=0x5865F2
    )
    embed.add_field(name="🎶 Music", value=(
        "`-p <song>` — Play a song\n"
        "`-skip` — Skip current song\n"
        "`-stop` — Stop & clear queue\n"
        "`-pause` — Pause\n"
        "`-resume` — Resume\n"
        "`-queue` — Show queue\n"
        "`-loop` — Toggle loop\n"
        "`-leave` — Leave voice\n"
        "`-clear` — Clear queue"
    ), inline=False)
    embed.add_field(name="⚙️ Utility", value=(
        "`-ping` — Check latency\n"
        "`-help` — Show this message"
    ), inline=False)
    embed.set_footer(text="🎧 DARKSIDE MUSIC | Made with ❤️ for Render")
    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name="-p to play music"))

# ===== START BOT =====
bot.run(os.getenv("DISCORD_TOKEN"))
