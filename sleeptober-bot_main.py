import asyncio # Locking write access.
import datetime as dt # Getting the date.
import json # De-/Serializing.
import os # Checking whether a file exists.
import statistics as stats # Computing median etc.
import collections
import random

import discord
from discord.ext import commands

# Path to file storing bot token.
CONFIG_FILE = "sleeptober-bot_config.json"
# Configuration will be loaded at startup.
CONFIG = {}

# Path to file storing sleep data.
DATA_FILE = "sleeptober-bot_data.json"
# Writer lock for data file.
DATA_FILE_LOCK = asyncio.Lock()

# A simple color palette for the bot to use.
COLORS = {
    "light": discord.Color.from_str("#C5D0DC"),
    "high":  discord.Color.from_str("#5BA2CD"),
    "low":   discord.Color.from_str("#3069B7"),
    "dark":  discord.Color.from_str("#29313D"),
}

COMMAND_PREFIX = ">>="

DESCRIPTION = """Sleeptober

Official 2024 Prompt List:

 1. sleep 8 hours   11. sleep 8 hours   21. sleep 8 hours
 2. sleep 8 hours   12. sleep 8 hours   22. sleep 8 hours
 3. sleep 8 hours   13. sleep 8 hours   23. sleep 8 hours
 4. sleep 8 hours   14. sleep 8 hours   24. sleep 8 hours
 5. sleep 8 hours   15. sleep 8 hours   25. sleep 8 hours
 6. sleep 8 hours   16. sleep 8 hours   26. sleep 8 hours
 7. sleep 8 hours   17. sleep 8 hours   27. sleep 8 hours
 8. sleep 8 hours   18. sleep 8 hours   28. sleep 8 hours
 9. sleep 8 hours   19. sleep 8 hours   29. sleep 8 hours
10. sleep 8 hours   20. sleep 8 hours   30. sleep 8 hours
                                        31. sleep 8 hours

            #Sleeptober  #Sleeptober2024

> Sleeptober was created as a challenge to improve one's sleeping skills and develop positive sleeping habits.

Source code: https://github.com/Strophox/sleeptober-bot
*This bot is developed heavily ad-hoc and just for fun :-)"""

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    description=DESCRIPTION,
    intents=intents,
)

SleepStats = collections.namedtuple("SleepStats", [
    "days",
    "min",
    "max",
    "mean",
    "median",
    "deviation",
    "deficit",
    "surplus",
    "score",
    "experimental_score",
])

def fmt_hours_f(hours):
    """Format 6.50069 hours as "6.50"."""
    return f"{hours:2.2f}"

def fmt_hours(hours):
    """Format 6.50069 hours as "6:30"."""
    minutes = round(hours * 60)
    hh = minutes // 60
    mm = minutes % 60
    return f"{hh}:{mm:02}"

def load_data():
    """Filesystem load of global sleep data."""
    with open(DATA_FILE, 'r') as file:
        data = json.load(file)
    return data

def store_data(data):
    """Filesystem store of global sleep data."""
    with open(DATA_FILE, 'w') as file:
        json.dump(data, file, indent=4)

def get_sleeptober_index():
    """Get the index of the currently relevant day (usually yesterday), or None if yesterday was not part of October."""
    yesterday = dt.datetime.now() - dt.timedelta(hours=22)
    if yesterday.month == 10:
        return yesterday.day - 1
    else:
        return None

def get_saturating_sleeptober_index():
    sleeptober_index = get_sleeptober_index()
    # FIXME What if the users queried this *before* October?
    return (30 if sleeptober_index is None else sleeptober_index)

def compute_sleep_stats(user_data):
    """Compute some SleepStats from user's raw hours-slept-each-night data with at least one data point."""
    hours = [h for h in user_data if h is not None]
    days_logged = len(hours)
    days_unlogged = len(user_data) - days_logged
    hours_min = min(hours)
    hours_max = max(hours)

    hours_mean = stats.mean(hours)
    hours_median = stats.median(hours)
    hours_variance = sum(h**2 for h in hours)/days_logged - hours_mean**2
    hours_deviation = hours_variance**.5

    hours_deficit = 0
    hours_surplus = 0
    LOWER = 8
    UPPER = 9
    for h in hours:
        if h < LOWER:
            hours_deficit += LOWER - h
        elif UPPER < h:
            hours_surplus += h - UPPER
    hours_deficit_copy = hours_deficit
    hours_surplus_copy = hours_surplus
    # Compute normal Sleeptober score,
    sleeptober_score = 1000 * days_logged - hours_deficit_copy - hours_surplus_copy / 2
    # Compute experimental Sleeptober score,
    placeholder_night = hours_mean - 3 * hours_deviation
    if placeholder_night < LOWER:
        hours_deficit_copy += days_unlogged*(LOWER - placeholder_night)
    elif UPPER < placeholder_night:
        hours_surplus_copy += days_unlogged*(placeholder_night - UPPER)
    experimental_score = 1000 - hours_deficit_copy - hours_surplus_copy / 2
    if days_unlogged > days_logged:
        experimental_score -= 500
    return SleepStats(
        days=days_logged,
        min=hours_min,
        max=hours_max,
        mean=hours_mean,
        median=hours_median,
        deviation=hours_deviation,
        deficit=hours_deficit,
        surplus=hours_surplus,
        score=sleeptober_score,
        experimental_score=experimental_score,
    )
    """
    # Notes about Abstract Score
    ## Criteria for scoring
    * Close to the idea of original Sleeptober ("Sleep 8 hours [every night]").
    * Close to the idea of having good sleep (*informal, research scientific criteria).
    * Reward number of days logged.
        - Indicative of user participation.
        - Bigger data/sample size to compute score from.
    * Punish sleep deficit.
        - Too little sleep is detrimental:
        ```
        0h "good luck"
        1h "any nap is better than no nap"
        2h "bruh"
        3h "💀"
        4h "it's joever"
        5h "oh no"
        6h "not good, but ≈minimum to function alright"
        7h "still fine, could be closer to 8"
        ```
    * Punish oversleeping.
        - Too much sleep may contribute to otherwise consistent, healthy sleep falling out of balance.
        - Sleeping way too much may cut into productivity of the next day.
        - If one slept too little the day before, sleeping more cannot proportionally 'make up' for last night's deficit.
        ```
        9h "nice, could be closer to 8"
        10h "bit long but could be less"
        11h "this is too long."
        12-14h "you've lost half your day."
        15-17h "oh no"
        17-24h "bruh"
        ```
    * Reward consistency / Punish inconsistency.
        - Consistent sleep is the best.
        - Sleeping 8h every day but offset by hours isn't actually healthy probably. (*time of sleep currently untracked)
        - TODO: Incorporate variance?
    """

@bot.event
async def on_ready():
    print(f"[ Logged in as {bot.user} (ID={bot.user.id}) ]")

@bot.command(aliases=["sleep","s",":3"])
async def slept(
        ctx,
        hours_slept: None | str = commands.parameter(description="Hours slept, given as a float in the range [0.0, 24.0] or in common `HH:MM` format."),
        night: None | str = commands.parameter(description="Night to manually write, in the range [1, <yesterday>], defaults to last night."),
    ):
    """Saves how many hours you slept last night."""
    print(f"[ s {hours_slept=} {night=} @ {dt.datetime.now().strftime('%Y-%m-%d_%Hh%Mm%S')} ]")
    # Compute who is being logged.
    if ctx.message.author.bot:
        await ctx.message.add_reaction('🤖')
        await ctx.message.reply("(Bots cannot participate in Sleeptober (yet))", delete_after=60)
        return
    author_user_id = ctx.message.author.id

    # Compute how many hours of sleep are being logged.
    if hours_slept is None:
        await ctx.message.reply(f"""Basic usage:
- \"I slept a healthy 8.5h last night <:bedge:1176108745865044011>\" → `{COMMAND_PREFIX}slept 8.5`
- \"Oof! I forgot to log 7h 56min for the 4th-to-5th night\" → `{COMMAND_PREFIX}slept 7:56 4`""")
        return

    # Try parsing as float.
    try:
        hours = float(hours_slept)
        if not 0 <= hours <= 24:
            await ctx.message.add_reaction('🙅')
            await ctx.message.reply("(Turns out you can only sleep between [0.0, 24.0]h a day)", delete_after=60)
            return
    except:
        # Try parsing as `HH:MM`.
        try:
            [hh,mm] = hours_slept.split(':')
            [hh,mm] = [int(hh), int(mm)]
            if not (0 <= hh < 24 and 0 <= mm < 60 or hh == 24 and mm == 0):
                raise ValueError
            hours = hh + mm / 60
        except:
            await ctx.message.add_reaction('🙅')
            await ctx.message.reply(f"(That's not a valid time in `HH:MM` or floating point format)", delete_after=60)
            return

    # Compute which day is being logged.
    if night is not None:
        date_index_cap = get_saturating_sleeptober_index()
        try:
            date_index = int(night) - 1
            if not (0 <= date_index <= date_index_cap):
                raise ValueError
        except:
            await ctx.message.add_reaction('🙅')
            await ctx.message.reply(f"(If you want to specify the night you're logging (second argument) it needs to be an integer in the range [1, {date_cap}])", delete_after=60)
            return
    else:
        # No day provided by user, default to setting last night's sleep.
        date_index = get_sleeptober_index()
        if date_index is None:
            await ctx.message.add_reaction('📆')
            await ctx.message.reply("(Last night wasn't part of Sleeptober - check again next year!)", delete_after=60)
            return

    # Do the logging.
    async with DATA_FILE_LOCK:
        data = load_data()
        data.setdefault(str(author_user_id), [None for _ in range(31)])[date_index] = hours
        store_data(data)

    # Reaction for visual feedback on success.
    if hours == 24.0:
        await ctx.message.add_reaction('💤')
    if hours == 0.0:
        await ctx.message.add_reaction('💀')
    elif hours < 4.0:
        await ctx.message.add_reaction("<:despairge:1212140064025485322>")
    elif hours < 6.0:
        await ctx.message.add_reaction("<:wokege:1176108188685324319>")
    else:
        await ctx.message.add_reaction("<:bedge:1176108745865044011>")


@bot.group(aliases=["p"], invoke_without_command=True)
async def profile(
        ctx,
        user: discord.User | None = commands.parameter(description="User whose profile to view."),
    ):
    """Shows how many hours you slept on each day of Sleeptober."""
    async with ctx.typing():
        # Load user data.
        if user is not None:
            target_user_id = user.id
        else:
            if ctx.message.author.bot:
                await ctx.message.add_reaction("🤖")
                return
            target_user_id = ctx.message.author.id
        data = load_data()
        user_data = data.get(str(target_user_id))

        # Generate profile.
        if user_data is None:
            text = f"...hasn't slept yet <:wokege:1176108188685324319>\n\nParticipate with `{COMMAND_PREFIX}slept`"
        else:
            # Truncate data.
            current_date_index = get_saturating_sleeptober_index()
            user_data = user_data[:current_date_index+1]

            # Add ASCII graph.
            (maxwidth_day_index, maxwidth_hours) = (len(str(len(user_data))), 5)
            text = "```c\n"
            text +=  f"{' ': >{maxwidth_day_index}}  {' ': >{maxwidth_hours}} ┍{7*'┯'}┳┳{14*'┯'}┑\n"
            for day_index, hours in enumerate(user_data):
                quarter_hours = round(hours * 4) if hours is not None else 0
                chars = ['│'] + 7*[' '] + 2*['┆'] + 14*[' '] + ['│']
                if 0 < quarter_hours:
                    if 2 <= quarter_hours:
                        chars[0] = '▐'
                        quarter_hours -= 2
                    else:
                        chars[0] = '🮇' # " ▕🮇🮈▐🮉🮊🮋█"
                        quarter_hours = 0
                i = 1
                while 0 < quarter_hours:
                    if 4 <= quarter_hours:
                        chars[i] = '█'
                        quarter_hours -= 4
                    else:
                        chars[i] = "▎▌▊"[quarter_hours-1] # " ▏▎▍▌▋▊▉█"
                        quarter_hours = 0
                    i += 1
                text += f"{day_index+1: >{maxwidth_day_index}}. {fmt_hours(hours) if hours is not None else '?': >{maxwidth_hours}} {''.join(chars)}\n"
            #text += f"{' ': >{maxwidth_day_index}}  {' ': >{maxwidth_hours}}  ┕{7*'┷'}┷┷{14*'┷'}┙\n"
            text += "```\n"

            # Add value summary.
            sleep_stats = compute_sleep_stats(user_data)
            text += f"""Sleep statistics
* `{sleep_stats.days}` days logged, average `{fmt_hours(sleep_stats.mean)}` h, median `{fmt_hours(sleep_stats.median)}` h.
* Total hours short of 8h `-{fmt_hours(sleep_stats.deficit)}` h, Total above 9h `+{fmt_hours(sleep_stats.surplus)}` h.
* Minimum `{fmt_hours(sleep_stats.min)}` h, maximum `{fmt_hours(sleep_stats.max)}` h, deviation `{fmt_hours(sleep_stats.deviation)}` h."""

        # Assemble and send embed.
        embed = discord.Embed(
            title="Personal Sleeptober Profile",
            description=text,
            color=COLORS['high']
        )
        await ctx.message.reply(embed=embed)

# @profile.command()
# async def raw(ctx):
#     """Get your sleep data as raw list."""
#     # Load user data.
#     if ctx.message.author.bot:
#         await ctx.message.add_reaction("🤖")
#         return
#     user_id = ctx.message.author.id
#     data = load_data()
#     user_data = data.get(str(user_id))
#
#     await ctx.message.add_reaction('✅')
#     await ctx.message.reply(f"Raw sleep data: `{user_data}`", delete_after=60)

@profile.command()
async def reset(
        ctx,
        confirm_code: str | None = commands.parameter(description="-"),
    ):
    """Used to reset (delete) one's data."""
    # Load user data.
    if ctx.message.author.bot:
        await ctx.message.add_reaction("🤖")
        return
    author_user_id = ctx.message.author.id
    i = (author_user_id >> 22) % 26
    confirm_code_expected = "abcdefghijklmnopqrstuvwxyzabc"[i:i+4]

    # Ask user for confirmation or delete directly.
    if confirm_code is None:
        await ctx.message.reply(f"Are you sure you want to delete your data? It will be lost forever! (A long time!) – Type `{COMMAND_PREFIX}profile reset {confirm_code_expected}` to confirm", delete_after=60)
    elif confirm_code == confirm_code_expected:
        # Do the deleting.
        async with DATA_FILE_LOCK:
            data = load_data()
            data.pop(str(author_user_id), None)
            store_data(data)
        await ctx.message.add_reaction('✅')
        await ctx.message.reply("(Your data has been reset)", delete_after=60)
    else:
        await ctx.message.add_reaction('❌')

@bot.command(aliases=["lb"])
async def leaderboard(
        ctx,
        sort: str | None = commands.parameter(description="Stat by which to sort."),
        #user: discord.User | None = commands.parameter(description="User whose position to view."), TODO: Remove debug.
    ):
    """Shows the current (global) Sleeptober leaderboard."""
    async with ctx.typing():
        # Load user data.
        #if user is not None: TODO: Remove debug.
        #    target_user_id = user.id
        #else:
        #    if ctx.message.author.bot:
        #        await ctx.message.add_reaction("🤖")
        #        return
        #    target_user_id = ctx.message.author.id
        if ctx.message.author.bot:
            await ctx.message.add_reaction("🤖")
            return
        target_user_id = ctx.message.author.id
        # Handle stat sorting and formatting mechanism.
        if sort is None:
            sort_stat = "score" # Last column is sleeptober_score.
            sort_down = True
            fmt_user_stats = lambda user_id, sleep_stats: f"""`{f'-{fmt_hours_f(sleep_stats.deficit)}': >6}` `{f'+{fmt_hours_f(sleep_stats.surplus)}': >6}` ~ {fmt_hours(sleep_stats.mean)} h. <@{user_id}> ({sleep_stats.days}d)"""
        else:
            if not (sort.startswith("+") or sort.startswith("-")) or sort[1:] not in SleepStats._fields:
                await ctx.message.reply(f"""Advanced leaderboard usage:
- "Sort downwards by 'Sleeptober' score" (default) → `{COMMAND_PREFIX}lb -score`.
- *Sort orders:* `-` for descending, `+` for ascending.
- *Sort criteria:* {", ".join(f"`{field}`" for field in SleepStats._fields)}.""")
                return
            sort_stat = sort[1:]
            sort_down = sort[0] == "-"
            if sort_stat in {"days","mean","deficit","surplus"}:
                fmt_user_stats = lambda user_id, sleep_stats: f"""`{f'-{fmt_hours_f(sleep_stats.deficit)}': >6}` `{f'+{fmt_hours_f(sleep_stats.surplus)}': >6}` ~ {fmt_hours(sleep_stats.mean)} h. <@{user_id}> ({sleep_stats.days}d)"""
            else:
                fmt_stats = {
                    # "days": lambda ss: f"{ss.days}d",
                    "min": lambda ss: f"min. {fmt_hours(ss.min)} h.",
                    "max": lambda ss: f"max. {fmt_hours(ss.max)} h.",
                    # "mean": lambda ss: f"avg. {fmt_hours(ss.mean)} h.",
                    "median": lambda ss: f"mdn. {fmt_hours(ss.median)} h.",
                    "deviation": lambda ss: f"dev. {fmt_hours(ss.deviation)} h.",
                    # "deficit": lambda ss: f"`{f'-{fmt_hours_f(ss.deficit)}': >6}`",
                    # "surplus": lambda ss: f"`{f'+{fmt_hours_f(ss.surplus)}': >6}`",
                    "score": lambda ss: f"`{ss.score:.03f}`✰",
                }.get(sort_stat, lambda ss: f"`{getattr(ss, sort_stat)}`(?)") # Fallback formatter.
                fmt_user_stats = lambda user_id, sleep_stats: f"""{fmt_stats(sleep_stats)} <@{user_id}> ({sleep_stats.days}d)"""

        data = load_data()
        if not data:
            text = "\n...seems like nobody has slept yet(??) (Be the first! `{COMMAND_PREFIX}sleep`)"
        else:
            current_date_index = get_saturating_sleeptober_index()
            # Load global leaderboard data, sorted as determined above.
            global_leaderboard = sorted(
                (
                    (
                        user_id,
                        compute_sleep_stats(user_data[:current_date_index+1])
                    )
                    for (user_id, user_data) in data.items()
                ),
                key=lambda id_stats: getattr(id_stats[1], sort_stat),
                reverse=sort_down
            )
            # Find user position on leaderboard.
            user_index = 0
            while user_index < len(global_leaderboard) and global_leaderboard[user_index][0] != str(target_user_id):
                user_index += 1
            # Format leaderboard preview.
            fmt_leaderboard_entries = lambda entries, rank_offset: '\n'.join(
                    f"""{1+rank_offset+i}. {"**" if rank_offset+i == user_index else ""}{fmt_user_stats(user_id, sleep_stats)}{"**" if rank_offset+i == user_index else ""}"""
                    for i, (user_id, sleep_stats) in enumerate(entries)
                )
            CAP_TOP_PREVIEW = 10
            RADIUS_CHUNK_WINDOW = 2
            if user_index-RADIUS_CHUNK_WINDOW <= CAP_TOP_PREVIEW+1:
                leaderboard_top = global_leaderboard[:max(CAP_TOP_PREVIEW,user_index+RADIUS_CHUNK_WINDOW+1)]
                leaderboard_chunk = []
            else:
                leaderboard_top = global_leaderboard[:CAP_TOP_PREVIEW]
                leaderboard_chunk = global_leaderboard[user_index-RADIUS_CHUNK_WINDOW:user_index+RADIUS_CHUNK_WINDOW+1]
            text = f"{fmt_leaderboard_entries(leaderboard_top, 0)}\n"
            text += "⋅ ⋅ ⋅\n"
            if leaderboard_chunk:
                text += f"{fmt_leaderboard_entries(leaderboard_chunk, user_index-RADIUS_CHUNK_WINDOW)}\n"
                if user_index+RADIUS_CHUNK_WINDOW+1 < len(global_leaderboard):
                    text += "⋅ ⋅ ⋅\n"
        if sort is not None:
            text += f"""-# Sorted in {"descending" if sort_down else "ascending"} order by `{sort_stat}`."""
        else:
            text += """-# Higher rank on the leaderboard is achieved by:
-# - Maximizing the number of days you logged,
-# - Minimizing the sum of hours you were short of sleeping 8h each night,
-# - Minimizing the sum of hours above 9h each night."""

        # Make mentions load correctly(??) (code inspired by /jackra1n/substiify-v2).
        mentions_str = ''.join(
            f"<@{user_id}>"
            for entries in [leaderboard_top,leaderboard_chunk]
            for (user_id, _) in entries
        )
        mentions_msg = await ctx.send(f"({random.choice('🌙🌓🌛🌕🌝🌗🌜🌑🌚🌘🌖🌒🌔')} loading names...)")
        await mentions_msg.edit(content=mentions_str)
        await mentions_msg.delete()

        # Assemble and send embed.
        embed = discord.Embed(
            title="D-INFK Sleeptober 2024 Leaderboard <:bedge:1176108745865044011>",
            description=text,
            color=COLORS['low']
        )
        await ctx.send(embed=embed)

@bot.command()
async def zzz(ctx):
    """[admin] Shuts down the bot."""
    # Load user id.
    if ctx.message.author.bot:
        await ctx.message.add_reaction('🤖')
        return
    author_user_id = ctx.message.author.id

    # Try shut down.
    if str(author_user_id) not in CONFIG['admin_ids']:
        await ctx.message.add_reaction('🔐')
        return
    else:
        await ctx.message.add_reaction('💤')
        exit() # FIXME: More graceful shutdown?

if __name__=="__main__":
    # Ensure data file is ready.
    if not os.path.exists(DATA_FILE):
        store_data({})

    # Load bot config from local file.
    with open(CONFIG_FILE, 'r') as file:
        CONFIG = json.load(file)

    # Start bot.
    bot.run(CONFIG['token'])
