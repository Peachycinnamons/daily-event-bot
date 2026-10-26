import discord
from discord.ext import commands, tasks
import os
import json

TOKEN = "MTU2NDI1Njk2NTE0Mjc4MTk5NQ.GH2nAa.4DSA2Y02YtOQKFkfIItPMJYi84pIKayBmCFFZo"

# Setup Bot
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

COUNTS_FILE = "counts.json"

def load_counts():
    if os.path.exists(COUNTS_FILE):
        with open(COUNTS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_counts(counts):
    with open(COUNTS_FILE, "w") as f:
        json.dump(counts, f)

user_weekly_counts = load_counts()

class EventView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.attendees = []

    @discord.ui.button(label="Join Event (Cap: 10)", style=discord.ButtonStyle.green, custom_id="join_event_button")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        current_count = user_weekly_counts.get(user_id, 0)

        # 1. Check weekly limit (4x per week cap)
        if current_count >= 4:
            await interaction.response.send_message("❌ You have reached your 4x weekly attendance limit!", ephemeral=True)
            return

        # 2. Check daily event cap (10 max per day)
        if len(self.attendees) >= 10:
            await interaction.response.send_message("❌ Event full! (10/10 capacity reached)", ephemeral=True)
            return

        # 3. Handle registration
        if user_id not in self.attendees:
            self.attendees.append(user_id)
            user_weekly_counts[user_id] = current_count + 1
            save_counts(user_weekly_counts)
            await interaction.response.send_message(f"✅ Slot confirmed! ({user_weekly_counts[user_id]}/4 sessions used this week)", ephemeral=True)
        else:
            await interaction.response.send_message("You are already registered for today's event.", ephemeral=True)

# Post daily event card command
@bot.command(name="startevent")
@commands.has_permissions(administrator=True)
async def start_event(ctx):
    embed = discord.Embed(
        title="📅 Daily Session RSVP",
        description="Click the button below to reserve your spot!\n\n• **10 attendees** max per day\n• **4 attendances** max per week",
        color=0x3498db
    )
    await ctx.send(embed=embed, view=EventView())

# Weekly count auto-reset every Sunday midnight (168 hours)
@tasks.loop(hours=168)
async def reset_weekly_limits():
    global user_weekly_counts
    user_weekly_counts = {}
    save_counts(user_weekly_counts)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    if not reset_weekly_limits.is_running():
        reset_weekly_limits.start()

bot.run(TOKEN)
