import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import openai
import asyncio
from collections import deque
from elevenlabs import generate, set_api_key, save
from flask import Flask
import threading

# ------------------ Load environment ------------------
load_dotenv("tokens.env")
AIKEY = os.getenv("OPENAI_API_KEY")
TOKEN = os.getenv("DISCORD_TOKEN")
VOICEKEY = os.getenv("ELEVENLABS_API_KEY")

GUILD_ID = 1444018728583823448  # Replace with your server ID
VOICE_NAME = "Adam"              # ElevenLabs voice
MODEL_NAME = "eleven_multilingual_v2"

# Set OpenAI and ElevenLabs API keys
openai_client = openai.OpenAI(api_key=AIKEY)
set_api_key(VOICEKEY)

# ------------------ Discord bot ------------------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Keep last 4 messages per user
user_memory = {}
MAX_MEMORY = 4

# ------------------ Background heartbeat ------------------
app = Flask("DiscordBot")

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

# ------------------ Helper: play audio ------------------
async def play_audio_in_channel(channel, audio_file):
    vc = channel.guild.voice_client
    if not vc:
        vc = await channel.connect()

    if vc.is_playing():
        vc.stop()

    vc.play(discord.FFmpegPCMAudio(executable="/usr/bin/ffmpeg", source=audio_file))
    while vc.is_playing():
        await asyncio.sleep(0.1)

# ------------------ Events ------------------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

# ------------------ Slash commands ------------------
@bot.tree.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):
    if interaction.user.voice:
        await interaction.user.voice.channel.connect()
        await interaction.response.send_message("Joined!")
    else:
        await interaction.response.send_message("You are not in a voice channel.", ephemeral=True)

@bot.tree.command(name="leave", description="Leave the voice channel")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Left the voice channel!")
    else:
        await interaction.response.send_message("I am not in a voice channel.", ephemeral=True)

# ------------------ Message command ------------------
@bot.command()
async def msg(ctx, *, message: str):
    user_id = ctx.author.id
    voice_channel = ctx.author.voice.channel if ctx.author.voice else None

    # Initialize user memory
    if user_id not in user_memory:
        user_memory[user_id] = deque(maxlen=MAX_MEMORY)

    user_memory[user_id].append({"role": "user", "content": message})

    # Build conversation for OpenAI
    messages = [{"role": "system", "content": (
        "You are a goofy, funny friend. You joke around, "
        "help when needed, and occasionally tease lightly, "
        "but stay friendly."
    )}] + list(user_memory[user_id])

    # Run OpenAI request in executor to avoid blocking
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
    )

    reply = response.choices[0].message.content
    user_memory[user_id].append({"role": "assistant", "content": reply})

    # Generate TTS using ElevenLabs
    audio = generate(
        text=reply,
        voice=VOICE_NAME,
        model=MODEL_NAME
    )
    save(audio, "reply.mp3")

    # Play in VC if user is connected, otherwise just send text
    if voice_channel:
        await play_audio_in_channel(voice_channel, "reply.mp3")
    else:
        await ctx.send(reply)

# ------------------ Run bot ------------------
bot.run(TOKEN)
