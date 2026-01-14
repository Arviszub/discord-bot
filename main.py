import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import openai
import asyncio
from collections import deque
import requests
from elevenlabs import save
from elevenlabs import AsyncElevenLabs

load_dotenv("tokens.env")
AIKEY = os.getenv("OPENAI_API_KEY")
TOKEN = os.getenv("DISCORD_TOKEN")
VOICEKEY = os.getenv("ELEVENLABS_API_KEY")

GUILD_ID = 1444018728583823448

client_api = openai.OpenAI(api_key=AIKEY)

aivoice_id = "nPczCjzI2devNBz1zQrb"

eleven_client = AsyncElevenLabs(api_key=VOICEKEY)

class MyClient(commands.Bot):
    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)


intents = discord.Intents.default()
intents.message_content = True
bot = MyClient(command_prefix="!", intents=intents)


user_memory = {} 

MAX_MEMORY = 4 

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

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


async def play_audio_in_channel(channel, audio):
    vc = channel.guild.voice_client

    if not vc:
        vc = await channel.connect()

    if vc.is_playing():
        vc.stop()

    vc.play(
        discord.FFmpegPCMAudio(
            executable=r"E:\ffmpeg\bin\ffmpeg.exe",
            source=audio
        )
    )

    while vc.is_playing():
        await asyncio.sleep(0.1)
    

@bot.command()
async def msg(ctx, *, message: str):
    user_id = ctx.author.id
    voice_channel = ctx.author.voice.channel if ctx.author.voice else None

    if user_id not in user_memory:
        user_memory[user_id] = deque(maxlen=MAX_MEMORY)

    user_memory[user_id].append({"role": "user", "content": message})
    messages = [{"role": "system", "content": (
        "You are a goofy, funny friend. You joke around, "
        "help when needed, and occasionally tease or gaslight lightly, "
        "but stay friendly."
    )}] + list(user_memory[user_id])

    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client_api.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
    )

    reply = response.choices[0].message.content

    user_memory[user_id].append({"role": "assistant", "content": reply})

    audio = eleven_client.text_to_speech.convert(
        voice_id=aivoice_id,
        model_id="eleven_multilingual_v2",
        text=reply
    )

    with open("reply.mp3", "wb") as f:
        async for chunk in audio:
            f.write(chunk)

    if voice_channel:
        await play_audio_in_channel(voice_channel, "reply.mp3")
    else:
        await ctx.send("Join a voice channel first!")
bot.run(TOKEN)
