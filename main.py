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
import hashlib
import random

load_dotenv("tokens.env")
AIKEY = os.getenv("OPENAI_API_KEY")
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1444018728583823448

client_api = openai.OpenAI(api_key=AIKEY)

class MyClient(commands.Bot):
    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

intents = discord.Intents.default()
intents.message_content = True
bot = MyClient(command_prefix="!", intents=intents)

MAX_CHAT_MEMORY = 6
user_memory = {}

def init_user(user_id):
    return {
        "chat": deque(maxlen=MAX_CHAT_MEMORY),
        "summary": "",
        "style": {}
    }

async def update_memory_summary(user_id):
    mem = user_memory[user_id]
    if len(mem["chat"]) < 6 or len(mem["chat"]) % 6 != 0:
        return
    convo = "\n".join(f"{m['role']}: {m['content']}" for m in mem["chat"])
    loop = asyncio.get_running_loop()
    summary_response = await loop.run_in_executor(
        None,
        lambda: client_api.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract stable long-term traits about the user from this conversation. Include personality, preferences, recurring jokes, name, dislikes. Keep it extremely short."},
                {"role": "user", "content": convo}
            ]
        )
    )
    mem["summary"] = summary_response.choices[0].message.content

app = Flask("DiscordBot")

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_flask, daemon=True).start()

async def play_audio_in_channel(channel, audio_file):
    vc = channel.guild.voice_client
    if not vc:
        vc = await channel.connect()
    if vc.is_playing():
        vc.stop()
    vc.play(discord.FFmpegPCMAudio(executable="/usr/bin/ffmpeg", source=audio_file))
    while vc.is_playing():
        await asyncio.sleep(0.1)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.tree.command(name="leave", description="Leave the voice channel")
async def leave(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Left the voice channel!")
    else:
        await interaction.response.send_message("I am not in a voice channel.", ephemeral=True)

@bot.command()
async def msg(ctx, *, message: str):
    user_id = ctx.author.id
    voice_channel = ctx.author.voice.channel if ctx.author.voice else None
    if user_id not in user_memory:
        user_memory[user_id] = init_user(user_id)
    mem = user_memory[user_id]
    mem["chat"].append({"role": "user", "content": message})
    if "call me" in message.lower():
        name = message.lower().split("call me")[-1].strip().split()[0]
        mem["style"]["preferred_name"] = name
    system_prompt = "You are a chaotic but loyal Discord gremlin. You joke around, tease lightly, help when needed, and always reference past interactions from memory. "
    system_prompt += f"Long-term memory about this user: {mem['summary'] or 'None yet.'}"
    if mem["style"].get("preferred_name"):
        system_prompt += f"\nAlways call the user {mem['style']['preferred_name']}."
    messages = [{"role": "system", "content": system_prompt}] + list(mem["chat"])
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client_api.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages
        )
    )
    reply = response.choices[0].message.content
    if random.random() < 0.3:
        reply += " 💀"
    mem["chat"].append({"role": "assistant", "content": reply})
    asyncio.create_task(update_memory_summary(user_id))
    tts_filename = f"tts_{hashlib.md5(reply.encode()).hexdigest()}.mp3"
    if not os.path.exists(tts_filename):
        tts = gTTS(text=reply, lang="en")
        tts.save(tts_filename)
    if voice_channel:
        await play_audio_in_channel(voice_channel, tts_filename)
    else:
        await ctx.send(reply)

bot.run(TOKEN)
