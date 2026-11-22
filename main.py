import datetime
import json
import os
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
MANILA_TZ = ZoneInfo("Asia/Manila")

COUNTS_FILE = "counts.json"
EVENTS_FILE = "events.json"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


def load_json_safe(filepath: str, default: dict) -> dict:
    if not os.path.exists(filepath):
        return dict(default)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else dict(default)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"⚠️ Failed to read {filepath} ({exc}); using default state.")
        return dict(default)


def save_json_safe(filepath: str, data: dict) -> None:
    tmp_path = f"{filepath}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, filepath)
    except OSError as exc:
        print(f"❌ Failed to write {filepath}: {exc}")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


user_weekly_counts: dict[str, int] = load_json_safe(COUNTS_FILE, {})
# Maps str(message_id) -> list[str] of user_ids
active_events: dict[str, list[str]] = load_json_safe(EVENTS_FILE, {})


class EventView(discord.ui.View):
    def __init__(self, attendees: list[str] | None = None):
        super().__init__(timeout=None)
        self.attendees: list[str] = list(attendees) if attendees else []

    def build_embed(self) -> discord.Embed:
        if self.attendees:
            attendee_list = "\n".join(
                [f"• <@{uid}> ({user_weekly_counts.get(uid, 0)}/4 sessions this week)" for uid in self.attendees]
            )
        else:
            attendee_list = "_No one has signed up yet._"

        return discord.Embed(
            title="📅 Daily RED BOX Attendance",
            description=(
                "Click the button below to reserve your spot!\n\n"
                f"• **Attendees Today ({len(self.attendees)}/10):**\n{attendee_list}\n\n"
                "• **Limits:** 10 max per day | 4 attendances max per week"
            ),
            color=0x3498DB,
        )

    @discord.ui.button(label="Join Event (Cap: 10)", style=discord.ButtonStyle.green, custom_id="join_event_button")
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = str(interaction.message.id) if interaction.message else ""
        # Always sync with latest persisted attendee list for this message
        self.attendees = list(active_events.get(msg_id, self.attendees))

        user_id = str(interaction.user.id)
        current_count = user_weekly_counts.get(user_id, 0)

        if user_id in self.attendees:
            await interaction.response.send_message("You are already registered for today's event.", ephemeral=True)
            return

        if current_count >= 4:
            await interaction.response.send_message(
                "❌ You have reached your 4x weekly attendance limit!", ephemeral=True
            )
            return

        if len(self.attendees) >= 10:
            await interaction.response.send_message("❌ Event full! (10/10 capacity reached)", ephemeral=True)
            return

        self.attendees.append(user_id)
        user_weekly_counts[user_id] = current_count + 1

        if msg_id:
            active_events[msg_id] = list(self.attendees)
            save_json_safe(EVENTS_FILE, active_events)

        save_json_safe(COUNTS_FILE, user_weekly_counts)

        await interaction.response.edit_message(embed=self.build_embed(), view=self)
        await interaction.followup.send(
            f"✅ Slot confirmed! ({user_weekly_counts[user_id]}/4 sessions used this week)", ephemeral=True
        )


async def publish_event_card(target: discord.abc.Messageable) -> discord.Message:
    view = EventView([])
    message = await target.send(embed=view.build_embed(), view=view)
    active_events[str(message.id)] = []
    save_json_safe(EVENTS_FILE, active_events)
    return message


@bot.command(name="startevent")
@commands.has_permissions(administrator=True)
async def start_event(ctx: commands.Context):
    await publish_event_card(ctx)


@bot.command(name="reset")
@commands.has_permissions(administrator=True)
async def reset_limits_manual(ctx: commands.Context):
    global user_weekly_counts
    user_weekly_counts = {}
    save_json_safe(COUNTS_FILE, user_weekly_counts)
    await ctx.send("🔄 Weekly attendance counts have been successfully **reset to 0** for all members!")


@tasks.loop(time=datetime.time(hour=7, minute=0, tzinfo=MANILA_TZ))
async def daily_event_deployment():
    now_pht = datetime.datetime.now(MANILA_TZ)
    if CHANNEL_ID == 0:
        print(f"[{now_pht.isoformat()}] ❌ CHANNEL_ID is 0; skipping 7:00 AM post.")
        return

    try:
        channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
        if not isinstance(channel, discord.abc.Messageable):
            print(f"[{now_pht.isoformat()}] ❌ Channel {CHANNEL_ID} is not messageable.")
            return

        await publish_event_card(channel)
        print(f"[{now_pht.isoformat()}] ✅ Sent daily event post to channel {CHANNEL_ID}.")
    except discord.Forbidden:
        print(f"[{now_pht.isoformat()}] ❌ Missing permission to send messages in channel {CHANNEL_ID}.")
    except Exception as exc:
        print(f"[{now_pht.isoformat()}] ❌ Failed to send daily event post: {exc}")


@daily_event_deployment.before_loop
async def before_daily_event_deployment():
    await bot.wait_until_ready()


@bot.command(name="checklimits")
@commands.has_permissions(administrator=True)
async def check_limits(ctx: commands.Context):
    current_counts = load_json_safe(COUNTS_FILE, {})
    maxed_out_users = [f"<@{uid}> ({count}/4 sessions)" for uid, count in current_counts.items() if count >= 4]

    if not maxed_out_users:
        await ctx.send("✅ No one has maxed out their 4x weekly limit yet!")
        return

    embed = discord.Embed(
        title="🛑 Users at Weekly Limit (4/4)",
        description="\n".join(maxed_out_users),
        color=0xE74C3C,
    )
    await ctx.send(embed=embed)


@bot.command(name="test7am")
@commands.has_permissions(administrator=True)
async def test_seven_am(ctx: commands.Context):
    now_pht = datetime.datetime.now(MANILA_TZ)
    next_run = daily_event_deployment.next_iteration

    if CHANNEL_ID == 0:
        msg = (
            f"⚠️ `CHANNEL_ID` is `0` (not configured).\n"
            f"• PHT Time: `{now_pht.isoformat()}`\n"
            f"• Loop Running: `{daily_event_deployment.is_running()}`\n"
            f"• Next Scheduled Run: `{next_run.isoformat() if next_run else 'N/A'}`"
        )
        print(f"[TEST7AM] {msg}")
        await ctx.send(msg)
        return

    try:
        channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
    except Exception as exc:
        msg = f"❌ Failed to fetch channel `{CHANNEL_ID}`: `{exc}`"
        print(f"[TEST7AM] {msg}")
        await ctx.send(msg)
        return

    perms_summary = "N/A (DM or non-guild channel)"
    missing_perms = []

    if isinstance(channel, discord.abc.GuildChannel) and channel.guild.me:
        perms = channel.permissions_for(channel.guild.me)
        needed = {
            "view_channel": perms.view_channel,
            "send_messages": perms.send_messages,
            "embed_links": perms.embed_links,
            "read_message_history": perms.read_message_history,
        }
        missing_perms = [name for name, allowed in needed.items() if not allowed]
        perms_summary = (
            f"view_channel={perms.view_channel}, "
            f"send_messages={perms.send_messages}, "
            f"embed_links={perms.embed_links}"
        )

    print(
        f"[TEST7AM] channel_id={CHANNEL_ID} | resolved={getattr(channel, 'name', type(channel).__name__)} | "
        f"perms=({perms_summary}) | missing={missing_perms} | next_run={next_run}"
    )

    await daily_event_deployment()

    status_line = (
        f"⚠️ Missing permissions: `{', '.join(missing_perms)}`"
        if missing_perms
        else "✅ Core channel permissions look good"
    )
    await ctx.send(
        f"🧪 **7:00 AM Task Diagnostic & Test Run**\n"
        f"• **PHT Time:** `{now_pht.isoformat()}`\n"
        f"• **Target Channel:** `<#{CHANNEL_ID}>` (`{CHANNEL_ID}`)\n"
        f"• **Permissions:** `{perms_summary}`\n"
        f"• **Permission Check:** {status_line}\n"
        f"• **Loop Running:** `{daily_event_deployment.is_running()}`\n"
        f"• **Next Scheduled Run:** `{next_run.isoformat() if next_run else 'N/A'}`"
    )


@tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=MANILA_TZ))
async def reset_weekly_limits():
    now_pht = datetime.datetime.now(MANILA_TZ)
    if now_pht.weekday() == 0:
        global user_weekly_counts
        user_weekly_counts = {}
        save_json_safe(COUNTS_FILE, user_weekly_counts)
        print(f"[{now_pht.isoformat()}] 🔄 Weekly limits reset for Monday.")


@reset_weekly_limits.before_loop
async def before_reset_weekly_limits():
    await bot.wait_until_ready()


@bot.event
async def on_ready():
    now_pht = datetime.datetime.now(MANILA_TZ)
    print(f"Logged in as {bot.user} | PHT clock: {now_pht.isoformat()} | CHANNEL_ID: {CHANNEL_ID}")

    # Register persistent view so buttons continue working across restarts
    bot.add_view(EventView())

    if not reset_weekly_limits.is_running():
        reset_weekly_limits.start()
    if not daily_event_deployment.is_running():
        daily_event_deployment.start()


if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ Error: TOKEN environment variable not found!")
