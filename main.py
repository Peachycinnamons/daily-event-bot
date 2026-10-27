import discord
from discord.ext import commands, tasks
import os
import json
import datetime
from zoneinfo import ZoneInfo  # Built-in Python 3.9+ timezone support

# Setup Bot securely using Render environment variables
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))  # Set your announcement channel ID in Render

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

    def build_embed(self):
        # Format the attendee list for today with times/names
        if self.attendees:
            attendee_list = "\n".join([f"• <@{uid}> ({user_weekly_counts.get(uid, 0)}/4 sessions this week)" for uid in self.attendees])
        else:
            attendee_list = "_No one has signed up yet._"

        embed = discord.Embed(
            title="📅 Daily Session RSVP",
            description=(
                "Click the button below to reserve your spot!\n\n"
                f"• **Attendees Today ({len(self.attendees)}/10):**\n{attendee_list}\n\n"
                "• **Limits:** 10 max per day | 4 attendances max per week"
            ),
            color=0x3498db
        )
        return embed

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
            
            # Update the message embed dynamically with the new attendee list
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
            await interaction.followup.send(f"✅ Slot confirmed! ({user_weekly_counts[user_id]}/4 sessions used this week)", ephemeral=True)
        else:
            await interaction.response.send_message("You are already registered for today's event.", ephemeral=True)

# Manual command to post the daily event card
@bot.command(name="startevent")
@commands.has_permissions(administrator=True)
async def start_event(ctx):
    view = EventView()
    await ctx.send(embed=view.build_embed(), view=view)

# Automated Daily Deployment Task (Runs daily at 7:00 AM Philippine Time)
@tasks.loop(time=datetime.time(hour=7, minute=0, tzinfo=ZoneInfo("Asia/Manila")))
async def daily_event_deployment():
    if CHANNEL_ID == 0:
        return
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        view = EventView()
        await channel.send(embed=view.build_embed(), view=view)

# Check who has maxed out their weekly limits
@bot.command(name="checklimits")
@commands.has_permissions(administrator=True)
async def check_limits(ctx):
    current_counts = load_counts()
    
    maxed_out_users = []
    for user_id, count in current_counts.items():
        if count >= 4:
            maxed_out_users.append(f"<@{user_id}> ({count}/4 sessions)")

    if not maxed_out_users:
        await ctx.send("✅ No one has maxed out their 4x weekly limit yet!")
        return

    embed = discord.Embed(
        title="🛑 Users at Weekly Limit (4/4)",
        description="\n".join(maxed_out_users),
        color=0xe74c3c
    )
    await ctx.send(embed=embed)
    
# Weekly count auto-reset every Sunday midnight Philippine Time
@tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("Asia/Manila")))
async def reset_weekly_limits():
    # Only run the reset if today is Sunday (weekday() == 6)
    if datetime.datetime.now(ZoneInfo("Asia/Manila")).weekday() == 6:
        global user_weekly_counts
        user_weekly_counts = {}
        save_counts(user_weekly_counts)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    if not reset_weekly_limits.is_running():
        reset_weekly_limits.start()
    if not daily_event_deployment.is_running():
        daily_event_deployment.start()

if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ Error: TOKEN environment variable not found!")
