# =========================
# IMPORTS
# =========================
import os
import discord
from discord.ext import commands
import yt_dlp
import asyncio
import threading
from flask import Flask

# =========================
# KEEP ALIVE (RENDER SUPPORT)
# =========================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

# =========================
# DISCORD SETUP
# =========================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix='-', intents=intents, help_command=None)

# Store looping state per guild
looping_guilds = {}

# =========================
# EVENTS
# =========================
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print("Bot is ready!")

# =========================
# COMMANDS
# =========================

# Ping
@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency * 1000)}ms")

# Help
@bot.command()
async def help(ctx):
    help_text = """
**🎵 Music Bot Commands**
- `-ping` → Check bot latency
- `-play <url>` → Play a YouTube song (supports cookies)
- `-stop` → Stop music and leave channel
- `-loop` → Toggle loop for current song
- `-help` → Show this message
"""
    await ctx.send(help_text)

# Play
@bot.command()
async def play(ctx, *, query):
    # Add 'ytsearch1:' to search YouTube
    ytdl_opts = {'format': 'bestaudio'}
    with yt_dlp.YoutubeDL(ytdl_opts) as ytdl:
        info = ytdl.extract_info(f"ytsearch1:{query}", download=False)
        url = info['entries'][0]['webpage_url']
    # Play the URL in voice
    voice_channel = ctx.author.voice.channel
    if ctx.voice_client is None:
        await voice_channel.connect()
    ctx.voice_client.stop()
    ctx.voice_client.play(discord.FFmpegPCMAudio(url))
    await ctx.send(f"Now playing: {url}")
    }

    # YouTube cookies support
    cookies_path = os.environ.get("YT_COOKIES")  # optional, set env var
    if cookies_path:
        ytdl_opts['cookiefile'] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']

        def after_playing(err):
            if err:
                print(f"Playback error: {err}")
            if looping_guilds.get(ctx.guild.id):
                # Replay the same song if loop enabled
                ctx.voice_client.play(discord.FFmpegPCMAudio(audio_url), after=after_playing)

        ctx.voice_client.stop()
        ctx.voice_client.play(discord.FFmpegPCMAudio(audio_url), after=after_playing)
        await ctx.send(f"▶️ Now playing: {info['title']}")
    except Exception as e:
        await ctx.send(f"❌ Could not play the song: {e}")

# Stop
@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        looping_guilds[ctx.guild.id] = False
        await ctx.voice_client.disconnect()
        await ctx.send("⏹ Stopped and disconnected from the voice channel.")
    else:
        await ctx.send("❌ I'm not in a voice channel.")

# Loop toggle
@bot.command()
async def loop(ctx):
    if ctx.voice_client is None or not ctx.voice_client.is_playing():
        return await ctx.send("❌ Nothing is playing to loop.")
    
    looping_guilds[ctx.guild.id] = not looping_guilds.get(ctx.guild.id, False)
    status = "enabled" if looping_guilds[ctx.guild.id] else "disabled"
    await ctx.send(f"🔁 Loop has been {status} for this song.")

# =========================
# RUN BOT
# =========================
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    print("❌ DISCORD_TOKEN environment variable not set!")
else:
    bot.run(DISCORD_TOKEN)


