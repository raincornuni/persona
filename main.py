import discord
from discord.ext import commands
import aiosqlite
import os

# Securely grab token from Pterodactyl's Startup panel
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="t!", intents=intents)

DB_FILE = "tuppers.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tuppers (
                user_id INTEGER,
                name TEXT,
                avatar_url TEXT,
                prefix TEXT,
                suffix TEXT,
                PRIMARY KEY (user_id, name)
            )
        ''')
        await db.commit()

@bot.event
async def on_ready():
    await init_db()
    print(f"✅ Bot successfully connected! Logged in as {bot.user.name}")

# --- COMMANDS ---
@bot.command(name="register")
async def register(ctx, name: str, brackets: str, avatar_url: str):
    if "text" not in brackets:
        await ctx.send("❌ Brackets format must contain 'text'. Example: `[text]`")
        return
    prefix, suffix = brackets.split("text", 1)
    async with aiosqlite.connect(DB_FILE) as db:
        try:
            await db.execute(
                "INSERT INTO tuppers (user_id, name, avatar_url, prefix, suffix) VALUES (?, ?, ?, ?, ?)",
                (ctx.author.id, name, avatar_url, prefix, suffix)
            )
            await db.commit()
            await ctx.send(f"✅ Registered **{name}**!")
        except aiosqlite.IntegrityError:
            await ctx.send(f"❌ You already have a tupper named **{name}**.")

@bot.command(name="remove")
async def remove(ctx, name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("DELETE FROM tuppers WHERE user_id = ? AND name = ?", (ctx.author.id, name))
        await db.commit()
        if cursor.rowcount > 0:
            await ctx.send(f"✅ Removed tupper **{name}**.")
        else:
            await ctx.send(f"❌ Could not find a tupper named **{name}**.")

@bot.command(name="list")
async def list_tuppers(ctx):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT name, prefix, suffix FROM tuppers WHERE user_id = ?", (ctx.author.id,)) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                await ctx.send("You have no tuppers registered.")
                return
            embed = discord.Embed(title=f"{ctx.author.display_name}'s Tuppers", color=discord.Color.blue())
            for name, prefix, suffix in rows:
                embed.add_field(name=name, value=f"Trigger: `{prefix}text{suffix}`", inline=False)
            await ctx.send(embed=embed)

# --- PROXY LOGIC ---
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT name, avatar_url, prefix, suffix FROM tuppers WHERE user_id = ?", (message.author.id,)) as cursor:
            tuppers = await cursor.fetchall()

    matched_tupper = None
    clean_content = ""
    for name, avatar_url, prefix, suffix in tuppers:
        if message.content.startswith(prefix) and message.content.endswith(suffix):
            start_idx = len(prefix)
            end_idx = len(message.content) - len(suffix) if suffix else len(message.content)
            if start_idx <= end_idx:
                matched_tupper = {"name": name, "avatar_url": avatar_url}
                clean_content = message.content[start_idx:end_idx].strip()
                break

    if matched_tupper and clean_content:
        try:
            await message.delete()
            webhooks = await message.channel.webhooks()
            webhook = next((wh for wh in webhooks if wh.user == bot.user), None)
            if not webhook:
                webhook = await message.channel.create_webhook(name="Tupper Proxy")
            await webhook.send(
                content=clean_content,
                username=matched_tupper["name"],
                avatar_url=matched_tupper["avatar_url"],
                allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception as e:
            print(f"Error handling proxy: {e}")

if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ CRITICAL ERROR: DISCORD_TOKEN is missing from Startup panel configuration.")
