import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import openai
import asyncio
from collections import deque
from gtts import gTTS
from flask import Flask
import threading

load_dotenv("tokens.env")
AIKEY = os.getenv("OPENAI_API_KEY")
TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = 1444018728583823448  # your server ID

client_api = openai.OpenAI(api_key=AIKEY)

class MyClient(commands.Bot):
    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

intents = discord.Intents.default()
intents.message_content = True
bot = MyClient(command_prefix="!", intents=intents)

user_memory = {}
MAX_MEMORY = 8

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

# ------------------ Background heartbeat ------------------
app = Flask("DiscordBot")

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask).start()

async def play_audio_in_channel(channel, audio_file):
    vc = channel.guild.voice_client
    if not vc:
        vc = await channel.connect()

    if vc.is_playing():
        vc.stop()

    vc.play(discord.FFmpegPCMAudio(executable="/usr/bin/ffmpeg", source=audio_file))
    while vc.is_playing():
        await asyncio.sleep(0.1)

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

async def update_memory_summary(user_id):
    mem = user_memory[user_id]

    if len(mem["chat"]) < 10:
        return

    convo = "\n".join(
        f"{m['role']}: {m['content']}" for m in mem["chat"]
    )

    loop = asyncio.get_running_loop()
    summary_response = await loop.run_in_executor(
        None,
        lambda: client_api.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize important long-term facts about the user: "
                        "preferences, personality, recurring jokes, dislikes, name, etc. "
                        "Keep it short."
                    )
                },
                {"role": "user", "content": convo}
            ]
        )
    )

    mem["summary"] = summary_response.choices[0].message.content

@bot.command()
async def msg(ctx, *, message: str):
    user_id = ctx.author.id
    voice_channel = ctx.author.voice.channel if ctx.author.voice else None

    if user_id not in user_memory:
        user_memory[user_id] = init_user(user_id)
    
    user_memory[user_id]["chat"].append({
        "role": "user",
        "content": message
    })

    mem = user_memory[user_id]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a goofy, funny friend. You joke around, "
                "help when needed, tease lightly, and act like you "
                "remember the user personally.\n\n"
                f"Long-term memory about this user:\n{mem['summary'] or 'None yet.'}"
            )
        }
    ] + list(mem["chat"])

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
    await update_memory_summary(user_id)
-
    tts = gTTS(text=reply, lang="en")
    tts.save("reply.mp3")

    if voice_channel:
        await play_audio_in_channel(voice_channel, "reply.mp3")
    else:
        await ctx.send(reply)  # fallback: text if not in VC

# ------------------ Run bot ------------------
bot.run(TOKEN)
