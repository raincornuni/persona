import discord
from discord.ext import commands
import aiosqlite
import re

# Insert your Discord Bot Token here
TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="t!", intents=intents)

DB_FILE = "tuppers.db"

# Initialize Database
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
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    print("Database initialized.")

# --- COMMANDS FOR MANAGING TUPPERS ---

@bot.command(name="register", help="Register a new tupper. Usage: t!register <name> <prefix>text<suffix> <avatar_url>")
async def register(ctx, name: str, brackets: str, avatar_url: str):
    # Parse brackets like [text] or t:text
    if "text" not in brackets:
        await ctx.send("❌ Brackets format must contain the word 'text'. Example: `[text]` or `t:text`")
        return
    
    prefix, suffix = brackets.split("text", 1)
    
    async with aiosqlite.connect(DB_FILE) as db:
        try:
            await db.execute(
                "INSERT INTO tuppers (user_id, name, avatar_url, prefix, suffix) VALUES (?, ?, ?, ?, ?)",
                (ctx.author.id, name, avatar_url, prefix, suffix)
            )
            await db.commit()
            await ctx.send(f"✅ Registered **{name}**! Trigger it using `{prefix}your message{suffix}`")
        except aiosqlite.IntegrityError:
            await ctx.send(f"❌ You already have a tupper named **{name}**. Use `t!remove {name}` first.")

@bot.command(name="remove", help="Remove a tupper by name. Usage: t!remove <name>")
async def remove(ctx, name: str):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("DELETE FROM tuppers WHERE user_id = ? AND name = ?", (ctx.author.id, name))
        await db.commit()
        if cursor.rowcount > 0:
            await ctx.send(f"✅ Removed tupper **{name}**.")
        else:
            await ctx.send(f"❌ Could not find a tupper named **{name}** belonging to you.")

@bot.command(name="list", help="List all your registered tuppers.")
async def list_tuppers(ctx):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT name, prefix, suffix FROM tuppers WHERE user_id = ?", (ctx.author.id,)) as cursor:
            rows = await cursor.fetchall()
            
            if not rows:
                await ctx.send("You have no tuppers registered. Create one with `t!register`!")
                return
            
            embed = discord.Embed(title=f"{ctx.author.display_name}'s Tuppers", color=discord.Color.blue())
            for name, prefix, suffix in rows:
                embed.add_field(name=name, value=f"Trigger: `{prefix}text{suffix}`", inline=False)
            await ctx.send(embed=embed)

# --- THE PROXY LOGIC ---

@bot.event
async def on_message(message):
    # Ignore bots to prevent infinite loops
    if message.author.bot or not message.guild:
        return

    # Process standard commands first
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # Fetch user's registered tuppers
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT name, avatar_url, prefix, suffix FROM tuppers WHERE user_id = ?", 
            (message.author.id,)
        ) as cursor:
            tuppers = await cursor.fetchall()

    # Check if the message matches any tupper's brackets
    matched_tupper = None
    clean_content = ""

    for name, avatar_url, prefix, suffix in tuppers:
        # Match prefix and suffix strictly if they exist
        if message.content.startswith(prefix) and message.content.endswith(suffix):
            # Extract the core message text inside the brackets
            start_idx = len(prefix)
            end_idx = len(message.content) - len(suffix) if suffix else len(message.content)
            
            # Ensure it's not an empty bracket match
            if start_idx <= end_idx:
                matched_tupper = {"name": name, "avatar_url": avatar_url}
                clean_content = message.content[start_idx:end_idx].strip()
                break

    # Proxy the message if a match was found
    if matched_tupper and clean_content:
        try:
            # 1. Delete original user message
            await message.delete()

            # 2. Find or create an available channel webhook
            webhooks = await message.channel.webhooks()
            webhook = None
            
            # Find a webhook created by this bot
            for wh in webhooks:
                if wh.user == bot.user:
                    webhook = wh
                    break
            
            # If none exists, make one
            if not webhook:
                webhook = await message.channel.create_webhook(name="Tupper Proxy")

            # 3. Fire the webhook acting as the tupper
            await webhook.send(
                content=clean_content,
                username=matched_tupper["name"],
                avatar_url=matched_tupper["avatar_url"],
                allowed_mentions=discord.AllowedMentions.none() # Prevents accidental ping bypasses
            )
        except discord.Forbidden:
            print(f"Missing permissions in channel {message.channel.name}")
