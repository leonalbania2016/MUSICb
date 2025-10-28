# bot.py
import os
import asyncio
import logging
import random
import threading
from collections import deque

from flask import Flask
from yt_dlp import YoutubeDL

import discord
from discord.ext import commands

# ---------- Basic logging ----------
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("lara_clone")

# ---------- Flask keep-alive (so Render sees a web process) ----------
app = Flask("keepalive")

@app.route("/")
def home():
    return "LaraClone is alive."

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    # bind to 0.0.0.0 so external world (Render) can probe it
    app.run(host="0.0.0.0", port=port)

# ---------- Bot configuration ----------
PREFIX = "-p"
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Per-guild state
class GuildState:
    def __init__(self):
        self.queue = deque()  # each item: dict with keys 'title','url','requester','webpage_url'
        self.current = None   # current track dict
        self.loop = False
        self.volume = 0.25

guilds = {}  # guild_id -> GuildState

def get_gstate(guild_id):
    if guild_id not in guilds:
        guilds[guild_id] = GuildState()
    return guilds[guild_id]

# yt-dlp options
YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",  # allow search when not a URL
    "source_address": "0.0.0.0",  # bind to IPv4
}

FFMPEG_OPTIONS = (
    "-vn "
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
)

ytdl = YoutubeDL(YTDL_OPTS)

# ---------- Audio helpers ----------
def ytdl_extract(info):
    # info is either url or search query; use yt-dlp to extract a playable URL & metadata
    try:
        data = ytdl.extract_info(info, download=False)
    except Exception as e:
        log.exception("yt-dlp extract failed")
        raise

    # If it's a search result, yt-dlp returns a 'entries' list
    if "entries" in data:
        entry = data["entries"][0]
    else:
        entry = data

    # obtain direct URL and title
    if "url" in entry:
        audio_url = entry["url"]
    else:
        # fallback to webpage_url
        audio_url = entry.get("webpage_url")

    title = entry.get("title", "Unknown title")
    webpage_url = entry.get("webpage_url", None)
    return {"title": title, "audio_url": audio_url, "webpage_url": webpage_url}

def create_player(audio_url, volume):
    before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    # Use FFmpegPCMAudio then wrap with PCMVolumeTransformer
    source = discord.FFmpegPCMAudio(audio_url, before_options=before_options, options="-vn")
    return discord.PCMVolumeTransformer(source, volume=volume)

# ---------- Playback flow ----------
async def ensure_voice(ctx):
    if ctx.voice_client and ctx.voice_client.is_connected():
        return ctx.voice_client
    if not ctx.author.voice:
        raise commands.CommandError("You are not in a voice channel.")
    channel = ctx.author.voice.channel
    vc = await channel.connect()
    return vc

async def start_playback(guild_id, vc):
    gstate = get_gstate(guild_id)
    if gstate.current is None:
        if not gstate.queue:
            return  # nothing to play
        # pop next
        gstate.current = gstate.queue.popleft()
    track = gstate.current

    # Create player
    player = create_player(track["audio_url"], gstate.volume)
    def after_playing(error):
        # called in event loop from discord
        fut = asyncio.run_coroutine_threadsafe(post_track_handler(guild_id, error), bot.loop)
        try:
            fut.result()
        except Exception:
            log.exception("Error in after_playing fut")

    vc.play(player, after=after_playing)

async def post_track_handler(guild_id, error):
    gstate = get_gstate(guild_id)
    if error:
        log.exception("Player error")
    # if looping, keep same current; else advance
    if gstate.loop:
        # re-create source and replay
        if gstate.current:
            guild = bot.get_guild(guild_id)
            if guild and guild.voice_client:
                vc = guild.voice_client
                if not vc.is_playing():
                    player = create_player(gstate.current["audio_url"], gstate.volume)
                    vc.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(post_track_handler(guild_id, e), bot.loop))
    else:
        # move to next
        gstate.current = None
        # if queue has items, start next
        guild = bot.get_guild(guild_id)
        if guild and guild.voice_client and gstate.queue:
            await start_playback(guild_id, guild.voice_client)
        else:
            # nothing more to play — optionally disconnect after timeout
            pass

# ---------- Commands ----------
@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (id: {bot.user.id})")
    bot.loop.create_task(status_task())
    log.info("Bot is ready.")

async def status_task():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"{PREFIX}play"))
        except Exception:
            pass
        await asyncio.sleep(600)

@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="LaraClone — Commands", color=discord.Color.blue())
    e.add_field(name=f"{PREFIX} <song or url>", value="Play a song or add it to queue", inline=False)
    e.add_field(name=f"{PREFIX}skip", value="Skip current song", inline=True)
    e.add_field(name=f"{PREFIX}pause", value="Pause", inline=True)
    e.add_field(name=f"{PREFIX}resume", value="Resume", inline=True)
    e.add_field(name=f"{PREFIX}stop", value="Stop and clear queue", inline=False)
    e.add_field(name=f"{PREFIX}queue", value="Show queue", inline=False)
    e.add_field(name=f"{PREFIX}np", value="Now playing", inline=True)
    e.add_field(name=f"{PREFIX}loop", value="Toggle loop", inline=True)
    e.add_field(name=f"{PREFIX}volume <0.01-1.0>", value="Set volume", inline=False)
    e.add_field(name=f"{PREFIX}shuffle", value="Shuffle queue", inline=True)
    e.add_field(name=f"{PREFIX}clear", value="Clear queue", inline=True)
    e.add_field(name=f"{PREFIX}leave", value="Disconnect bot from voice", inline=False)
    await ctx.send(embed=e)

@bot.command(name="volume")
async def volume_cmd(ctx, vol: float):
    gstate = get_gstate(ctx.guild.id)
    if vol < 0 or vol > 2:
        await ctx.send("Volume must be between 0 and 2 (2 = 200%).")
        return
    gstate.volume = vol
    vc = ctx.guild.voice_client
    if vc and vc.source:
        try:
            vc.source.volume = vol
        except Exception:
            pass
    await ctx.send(f"Volume set to {vol*100:.0f}%")

@bot.command(name="shuffle")
async def shuffle_cmd(ctx):
    gstate = get_gstate(ctx.guild.id)
    random.shuffle(gstate.queue)
    await ctx.send("Queue shuffled.")

@bot.command(name="clear")
async def clear_cmd(ctx):
    gstate = get_gstate(ctx.guild.id)
    gstate.queue.clear()
    await ctx.send("Queue cleared.")

@bot.command(name="loop")
async def loop_cmd(ctx):
    gstate = get_gstate(ctx.guild.id)
    gstate.loop = not gstate.loop
    await ctx.send(f"Loop is now {'ON' if gstate.loop else 'OFF'}")

@bot.command(name="np")
async def now_playing(ctx):
    gstate = get_gstate(ctx.guild.id)
    if gstate.current:
        t = gstate.current
        await ctx.send(f"Now playing: **{t['title']}** — requested by {t['requester'].mention}\n{t.get('webpage_url','')}")
    else:
        await ctx.send("Nothing is playing right now.")

@bot.command(name="queue")
async def queue_cmd(ctx):
    gstate = get_gstate(ctx.guild.id)
    if not gstate.queue:
        await ctx.send("Queue is empty.")
        return
    description = ""
    for i, t in enumerate(list(gstate.queue)[:10], start=1):
        description += f"{i}. {t['title']} — {t['requester'].mention}\n"
    if len(gstate.queue) > 10:
        description += f"...and {len(gstate.queue)-10} more."
    await ctx.send(f"Queue:\n{description}")

@bot.command(name="pause")
async def pause_cmd(ctx):
    vc = ctx.guild.voice_client
    if not vc or not vc.is_playing():
        await ctx.send("Nothing is playing.")
        return
    vc.pause()
    await ctx.send("Paused.")

@bot.command(name="resume")
async def resume_cmd(ctx):
    vc = ctx.guild.voice_client
    if not vc or not vc.is_paused():
        await ctx.send("Nothing to resume.")
        return
    vc.resume()
    await ctx.send("Resumed.")

@bot.command(name="skip")
async def skip_cmd(ctx):
    vc = ctx.guild.voice_client
    if not vc or not vc.is_playing():
        await ctx.send("Nothing is playing.")
        return
    vc.stop()
    await ctx.send("Skipped.")

@bot.command(name="stop")
async def stop_cmd(ctx):
    vc = ctx.guild.voice_client
    gstate = get_gstate(ctx.guild.id)
    gstate.queue.clear()
    gstate.current = None
    if vc:
        await vc.disconnect()
    await ctx.send("Stopped playback and cleared queue.")

@bot.command(name="leave")
async def leave_cmd(ctx):
    vc = ctx.guild.voice_client
    if not vc:
        await ctx.send("Bot is not in a voice channel.")
        return
    await vc.disconnect()
    await ctx.send("Left voice channel.")

@bot.command(name="play", aliases=["p"])
async def play_cmd(ctx, *, query: str):
    """Play a song from query (URL or text)."""
    # ensure user is in voice
    if not ctx.author.voice:
        await ctx.send("You must be in a voice channel to use this command.")
        return
    try:
        vc = await ensure_voice(ctx)
    except commands.CommandError as e:
        await ctx.send(str(e))
        return

    # fetch info using yt_dlp (works for URLs and search queries)
    msg = await ctx.send("🔎 Searching...")
    try:
        info = ytdl_extract(query)
    except Exception as e:
        await msg.edit(content=f"❌ Could not find/play: {e}")
        return

    track = {
        "title": info["title"],
        "audio_url": info["audio_url"],
        "webpage_url": info.get("webpage_url"),
        "requester": ctx.author
    }

    gstate = get_gstate(ctx.guild.id)
    # if nothing is playing and queue empty, start immediately
    if (not gstate.current) and (not vc.is_playing()):
        gstate.current = track
        await msg.edit(content=f"▶️ Now playing: **{track['title']}** (requested by {ctx.author.mention})")
        try:
            await start_playback(ctx.guild.id, vc)
        except Exception:
            log.exception("Failed to start playback")
            await msg.edit(content="❌ Failed to start playback.")
            gstate.current = None
    else:
        gstate.queue.append(track)
        await msg.edit(content=f"➕ Added to queue: **{track['title']}** (position {len(gstate.queue)})")

# ---------- Error handler ----------
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing argument.")
        return
    log.exception("Command error")
    await ctx.send(f"Error: {str(error)}")

# ---------- Start Flask thread then run bot ----------
if __name__ == "__main__":
    # Start flask in separate thread so Render health check sees a web process
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        log.error("DISCORD_TOKEN not set in environment.")
        raise SystemExit("DISCORD_TOKEN not set.")

    bot.run(TOKEN)
