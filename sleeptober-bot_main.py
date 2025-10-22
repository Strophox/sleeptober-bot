import asyncio # Locking write access.
import datetime as dt # Getting the date.
import json # De-/Serializing.
import os # Checking whether a file exists.
import statistics as stats # Computing median etc.
import math # math.prod
import collections
import random

import discord
from discord.ext import commands

# Custom datatype.
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
    "legacy_score",
    "experimental_score",
    "debug",
])

# Path to the file that stores the bot token and user IDs of privileged/admin users.
CONFIG_FILE = "sleeptober-bot_config.json"
# Global configuration will be initialized/loaded at startup.
CONFIG = {}

# Path to the file that stores all the sleep data.
DATA_FILE = "sleeptober-bot_data.json"
# Global writer lock for data file.
DATA_FILE_LOCK = asyncio.Lock()

# A simple color palette for the bot to use.
COLORS = {
    "light": discord.Color.from_str("#C5D0DC"), # Almost white.
    "high":  discord.Color.from_str("#5BA2CD"), # Light blue.
    "low":   discord.Color.from_str("#3069B7"), # Blue.
    "dark":  discord.Color.from_str("#29313D"), # Almost black.
}

# Some custom emojis to be used.
EMOJIS = {
    "bedge": "<:bedge:1176108745865044011>",
    "wokege": "<:wokege:1176108188685324319>",
    "despairge": "<:despairge:1212140064025485322>",
}

# Bot prefix.
COMMAND_PREFIX = ">>="

# Bot description for the `help` menu.
DESCRIPTION = f"""Sleeptober

Official 2025 Prompt List:

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

            #Sleeptober  #Sleeptober2025

> Sleeptober was created as a challenge to improve one's sleeping skills and develop positive sleeping habits.

* To reset / permanently delete your data see `{COMMAND_PREFIX}profile reset`.
* Source code: https://github.com/Strophox/sleeptober-bot
* This bot is developed heavily ad-hoc and just for fun :-)"""

# discord.py boilerplate.
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix=COMMAND_PREFIX,
    description=DESCRIPTION,
    intents=intents,
)

def fmt_hours_f(hours):
    """E.g. format 6.50069 hours as "6.50"."""
    return f"{hours:2.2f}"

def fmt_hours(hours):
    """E.g. format 6.50069 hours as "6:30"."""
    minutes = round(hours * 60)
    return f"{minutes // 60}:{minutes % 60:02}"

def load_data():
    """File system load of sleep data."""
    with open(DATA_FILE, 'r') as file:
        data = json.load(file)
    return data

def store_data(data):
    """File system store of sleep data."""
    with open(DATA_FILE, 'w') as file:
        json.dump(data, file, indent=4)

def get_sleeptober_index():
    """Get the index of the currently relevant day (usually yesterday), or None if yesterday was not part of October."""
    # FIXME: We're manually correcting for UTC+2 hour difference.
    yesterday = dt.datetime.now() - dt.timedelta(hours=22)
    if yesterday.month == 10:
        return yesterday.day - 1 # Index into October.
    else:
        return None

def get_saturating_sleeptober_index():
    sleeptober_index = get_sleeptober_index()
    # FIXME: What if the users queried this *before* October tho?
    # NOTE from future me: anytime is technically always after October.
    return (30 if sleeptober_index is None else sleeptober_index)

def compute_sleep_stats(user_data):
    """Compute some SleepStats from user's raw hours-slept-each-night data with at least one data point."""
    hours = [h for h in user_data if h is not None]

    days_logged = len(hours)
    days_unlogged = get_saturating_sleeptober_index()+1 - days_logged

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

    # Compute outdated Sleeptober score.
    legacy_score = 1000 * days_logged - hours_deficit - hours_surplus / 2

    # Compute main Sleeptober score.
    # NOTE: This scoring method boils down to
    #     some_constant - hours_deficit - hours_surplus / 2
    # * However, we add some ~hours_deficit for each night the user hasn't logged,
    #   by approximating that they slept (hours_mean - 2 * hours_standard_deviation) on those nights.
    #   (I think this should generally incentivize continuing to log your sleep
    #    without punishing it too harshly otherwise? :)
    PUNISH_DEFICIT = 1
    # The following choice of factor guarantees that sleeping 0h (deficit) and 24h (surplus) is punished equally
    PUNISH_SURPLUS = LOWER / (24 - UPPER)
    # We assume the worst sleep to lie within 2 standard deviations (covers '95%').
    PUNISH_UNLOGGED = 2 * hours_deviation
    # Start computing adjusted deficit/surplus by imputing sleep data for unlogged days.
    hours_deficit_adjusted_for_unlogged = hours_deficit
    hours_surplus_adjusted_for_unlogged = hours_surplus
    # Maximize loss depending on whether score is worse on lower or upper bound within the range created by PUNISH_UNLOGGED standard deviation range around user's sleep mean.
    if hours_mean <= LOWER + (UPPER - LOWER) * PUNISH_DEFICIT / (PUNISH_DEFICIT + PUNISH_SURPLUS):
        hours_deficit_adjusted_for_unlogged += days_unlogged * PUNISH_UNLOGGED
    else:
        hours_surplus_adjusted_for_unlogged += days_unlogged * PUNISH_UNLOGGED
    # The following choice of factor guarantees the score is always nonnegative, and exactly zero if the user sleeps 0h or 24h (both lead to maximal loss) each night.
    SCORE_OFFSET = 31 * LOWER * PUNISH_DEFICIT
    sleeptober_score = SCORE_OFFSET - hours_deficit_adjusted_for_unlogged * PUNISH_DEFICIT - hours_surplus_adjusted_for_unlogged * PUNISH_SURPLUS
    # HACK: Punish user if less than half of days so far not logged...
    if days_unlogged > days_logged:
        sleeptober_score /= 2

    # Compute experimental Sleeptober score.
    # NOTE: This scoring method boils down to
    #    (1 + hours_standard_deviation) * (1 + abs(8 - hours_mean)) * (1 + number_days_not_logged)
    # However, this gives us a number between `1` and some maximum `N` (with larger being 'worse').
    # We flip and normalize this so we get a number between `0` and `1000`.

    mean_heuristic      = (abs(diff)/8 if (diff:=hours_mean - LOWER) < 0 else abs(diff)/(24-LOWER))
    deviation_heuristic = hours_deviation / 12
    notlogged_heuristic = days_unlogged / 31
    # These heuristics variables should all normalized to the interval [0, 1].
    heuristics = [mean_heuristic, deviation_heuristic, notlogged_heuristic]
    experimental_score = round(
        ( math.prod(1+h for h in heuristics) - 1 )
      / ( 2**len(heuristics)                 - 1 )
      * 2**16
    )

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
        legacy_score=legacy_score,
        experimental_score=experimental_score,
        debug=heuristics,
    )

@bot.event
async def on_ready():
    print(f"[ '{bot.user}' ({bot.user.id}) is ready. ]")

@bot.command(aliases=["sleep","s",":3"])
async def slept(
        ctx,
        hours_slept: None | str = commands.parameter(description="Hours slept, given as a float in the range [0.0, 24.0] or in common `HH:MM` format."),
        night: None | str = commands.parameter(description="Night to manually write, in the range [1, <yesterday>], defaults to last night."),
    ):
    """Logs how many hours one slept last night."""
    print(f"[ s {hours_slept=} {night=} @ {dt.datetime.now().strftime('%Y-%m-%d_%Hh%Mm%S')} ]") # (Log to console.)

    # Compute who is being logged.
    if ctx.message.author.bot:
        await ctx.message.add_reaction('🤖')
        await ctx.message.reply("(Bots cannot participate in Sleeptober (yet))", delete_after=60)
        return
    author_user_id = ctx.message.author.id

    # Compute how many hours of sleep are being logged.
    if hours_slept is None:
        await ctx.message.reply(f"""Basic usage:
- "I slept a healthy 8.5h last night {EMOJIS["bedge"]}" → `{COMMAND_PREFIX}slept 8.5`
- "Oof! I forgot to log 7h 56min for the 4th-to-5th night" → `{COMMAND_PREFIX}slept 7:56 4`""")
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
            if not ((0 <= hh < 24 and 0 <= mm < 60) or (hh == 24 and mm == 0)):
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
            # User must have tried indexing into October and up to today's index.
            if not (0 <= date_index <= date_index_cap):
                raise ValueError
        except:
            await ctx.message.add_reaction('🙅')
            await ctx.message.reply(f"(If you want to specify the night you're logging (second argument) it needs to be an integer in the range [1, {date_index_cap+1}])", delete_after=60)
            return
    else:
        # No day provided by user, default to setting last night's sleep.
        date_index = get_sleeptober_index()
        if date_index is None:
            await ctx.message.add_reaction('📆')
            await ctx.message.reply("(Last night wasn't part of Sleeptober - check again next year!)", delete_after=60)
            return

    # Save new sleep data point.
    async with DATA_FILE_LOCK:
        data = load_data()
        data.setdefault(str(author_user_id), [None for _ in range(31)])[date_index] = hours
        store_data(data)

    # Reaction for visual feedback on success.
    if hours == 0.0:
        await ctx.message.add_reaction('💀')
    elif hours < 4.0:
        await ctx.message.add_reaction(EMOJIS["despairge"])
    elif hours < 6.0:
        await ctx.message.add_reaction(EMOJIS["wokege"])
    else: # hours >= 6.0
        await ctx.message.add_reaction(EMOJIS["bedge"])
    if hours == 24.0:
        await ctx.message.add_reaction('💤')


@bot.group(aliases=["p"], invoke_without_command=True)
async def profile(
        ctx,
        user: discord.User | None = commands.parameter(description="User whose profile to view."),
    ):
    """Shows how many hours one slept each night of Sleeptober."""
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
            text = f"...not slept yet {EMOJIS['wokege']}\n\n(For usage see `{COMMAND_PREFIX}slept`)"
        else:
            # Start building full text.
            text = ""

            # Truncate data up to current day of Sleeptober.
            user_data = user_data[:get_saturating_sleeptober_index()+1]

            # Special text for Sleeptober completion.
            fully_slept = sum(1 for x in user_data if x is not None) == 31
            if fully_slept:
                text += f"""### *⋆ ﾟ☁ ｡✧ fully slept ★ ﾟ☾｡⋆*
-# We hope you had fun and wish you much success
-# in future endeavours of becoming well-rested {EMOJIS['bedge']}💤\n"""

            # Build ASCII graph.
            text += "```c\n"

            maxwidth_day_index = len(str(len(user_data)))
            maxwidth_hours = 5

            # Upper frame.
            text += f"{' ': >{maxwidth_day_index}}  {' ': >{maxwidth_hours}} ┍{7*'┯'}┳┳{14*'┯'}┑\n"

            # One row for each day.
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

            # Lower frame if Sleeptober is over.
            sleeptober_over = len(user_data) == 31
            if sleeptober_over:
                text += f"{' ': >{maxwidth_day_index}}  {' ': >{maxwidth_hours}} ┕{7*'┷'}┻┻{14*'┷'}┙\n"
            text += "```\n"

            # Add final value summary.
            sleep_stats = compute_sleep_stats(user_data)
            text += f"""Sleep statistics
* `{sleep_stats.days}` days logged, Mean `{fmt_hours(sleep_stats.mean)}` h, Median `{fmt_hours(sleep_stats.median)}` h.
* Total short of 8h `-{fmt_hours(sleep_stats.deficit)}` h, Total above 9h `+{fmt_hours(sleep_stats.surplus)}` h.
* Min `{fmt_hours(sleep_stats.min)}` h, Max `{fmt_hours(sleep_stats.max)}` h, Deviation `{fmt_hours(sleep_stats.deviation)}` h."""

        embed = discord.Embed(
            title="Personal Sleeptober Profile",
            description=text,
            color=COLORS['high']
        )
        await ctx.message.reply(embed=embed)

@profile.command()
async def raw(ctx):
    """Get your sleep data as raw list."""
    # NOTE this sub-command technically excludes the user with username "raw" from querying their profile with ">>=profile raw". Sorry!
    # Load user data.
    if ctx.message.author.bot:
        await ctx.message.add_reaction("🤖")
        return
    user_id = ctx.message.author.id
    data = load_data()
    user_data = data.get(str(user_id))

    await ctx.message.add_reaction('✅')
    await ctx.message.reply(f"Raw sleep data: `{user_data}`", delete_after=120)

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

    # We ask the user to confirm their data deletion with a semi-fancy password.
    i = (author_user_id >> 22) % 26
    confirm_code_expected = "abcdefghijklmnopqrstuvwxyzab"[i:i+4]

    if confirm_code is None:
        await ctx.message.reply(f"Are you sure you want to delete your data? It will be lost forever! (A long time!) – Type `{COMMAND_PREFIX}profile reset {confirm_code_expected}` to confirm", delete_after=60)
    elif confirm_code == confirm_code_expected:
        # Delete from database.
        async with DATA_FILE_LOCK:
            data = load_data()
            data.pop(str(author_user_id), None)
            store_data(data)
        await ctx.message.add_reaction('✅')
        await ctx.message.reply("(Your data has been reset)", delete_after=60)
    else:
        # Wrong password.
        await ctx.message.add_reaction('❌')

@bot.command(aliases=["lb"])
async def leaderboard(
        ctx,
        sort_criteria: str | None = commands.parameter(description="Leaderboard sorting: Stat and order with which to sort."),
        min_days: int | None = commands.parameter(default=1, description="Leaderboard filter: Minimum number of days logged."),
        show_top_n: int | None = commands.parameter(default=10, description="Leaderboard preview size: How many top users to show."), # FIXME This could make the message too long with large enough leaderboard and show_top_n.
    ):
    """Shows the current, global Sleeptober user rankings."""
    # FIXME Please simplify/prettify this function :((
    async with ctx.typing():
        # Load user data.
        if ctx.message.author.bot:
            await ctx.message.add_reaction("🤖")
            return
        target_user_id = ctx.message.author.id

        current_date_index = get_saturating_sleeptober_index()
        min_days = max(0, min(min_days, current_date_index+1))

        # Handle stat sorting and formatting mechanism.
        # Initialize standard user stats formatter.
        fmt_user_stats = lambda user_id, sleep_stats: f"""`{f'-{fmt_hours(sleep_stats.deficit)}': >6}` `{f'+{fmt_hours(sleep_stats.surplus)}': >6}` ~ {fmt_hours(sleep_stats.mean)} h. <@{user_id}> ({sleep_stats.days}d)"""
        if sort_criteria is None:
            sort_stat = "score"
            sort_down = True
        else:
            if not (sort_criteria.startswith("+") or sort_criteria.startswith("-")) or sort_criteria[1:] not in SleepStats._fields:
                await ctx.message.reply(f"""Advanced leaderboard usage: `{COMMAND_PREFIX}lb sortOrderAndStat minDaysLogged showTopUsers`
- *Sort orders:* `-` for descending, `+` for ascending.
- *Statistics to sort by:* {", ".join(f"`{field}`" for field in SleepStats._fields)}.
Examples:
- "Sort downwards by average sleep" → `{COMMAND_PREFIX}lb -mean`.
- "Sleep deviation for people who slept at least 7 days in ascending order" → `{COMMAND_PREFIX}lb +deviation 7`.
- "Basically show the entire leaderboard (≥0 days logged, ≤999 people)" → `{COMMAND_PREFIX}lb -score 0 999`.""")
                return
            sort_stat = sort_criteria[1:]
            sort_down = sort_criteria[0] == "-"
            if sort_stat not in {"days","mean","deficit","surplus"}:
                fmt_stats = {
                    # "days": lambda ss: f"{ss.days}d",
                    "min": lambda ss: f"min. {fmt_hours(ss.min)} h.",
                    "max": lambda ss: f"max. {fmt_hours(ss.max)} h.",
                    # "mean": lambda ss: f"avg. {fmt_hours(ss.mean)} h.",
                    "median": lambda ss: f"mdn. {fmt_hours(ss.median)} h.",
                    "deviation": lambda ss: f"dev. {fmt_hours(ss.deviation)} h.",
                    # "deficit": lambda ss: f"`{f'-{fmt_hours_f(ss.deficit)}': >6}`",
                    # "surplus": lambda ss: f"`{f'+{fmt_hours_f(ss.surplus)}': >6}`",
                    "score": lambda ss: f"`{ss.score:.02f}`☆",
                }.get(sort_stat, lambda ss: f"`{getattr(ss, sort_stat)}`(?)") # Fallback formatter.
                fmt_user_stats = lambda user_id, sleep_stats: f"""{fmt_stats(sleep_stats)} <@{user_id}> ({sleep_stats.days}d)"""

        if sort_criteria is not None:
            text = f"""-# Sorted in {"descending" if sort_down else "ascending"} order by `{sort_stat}`{f" (and ≥{min_days}d)" if min_days > 1 else ""}.\n"""
        else:
            text = """-# *Shown:* `-deficit` `+surplus` ~ avg. sleep <user> (days logged).\n"""

        data = load_data()
        if not data:
            text += f"\n...seems like nobody has slept yet(??) (be the first → `{COMMAND_PREFIX}slept`)\n"
            mentions_str = ""
        else:
            # Load global leaderboard data, sorted as determined above.
            global_leaderboard = sorted(
                (
                    (
                        user_id,
                        sleep_stats,
                    )
                    for (user_id, user_data) in data.items()
                    if (sleep_stats:=compute_sleep_stats(user_data[:current_date_index+1])).days >= min_days
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
            show_top_n = max(show_top_n, 0)
            USER_PREVIEW_WINDOW = 2
            if user_index-USER_PREVIEW_WINDOW <= show_top_n+1:
                leaderboard_top = global_leaderboard[:max(show_top_n,user_index+USER_PREVIEW_WINDOW+1)]
                leaderboard_chunk = []
            else:
                leaderboard_top = global_leaderboard[:show_top_n]
                leaderboard_chunk = global_leaderboard[user_index-USER_PREVIEW_WINDOW:user_index+USER_PREVIEW_WINDOW+1]
            text += f"{fmt_leaderboard_entries(leaderboard_top, 0)}\n"
            if len(leaderboard_top) < len(global_leaderboard):
                text += "⋅ ⋅ ⋅\n"
            if leaderboard_chunk:
                text += f"{fmt_leaderboard_entries(leaderboard_chunk, user_index-USER_PREVIEW_WINDOW)}\n"
                if user_index+USER_PREVIEW_WINDOW+1 < len(global_leaderboard):
                    text += "⋅ ⋅ ⋅\n"

            # Make mentions load correctly(??) (code inspired by /jackra1n/substiify-v2).
            mentions_str = ''.join(
                f"<@{user_id}>"
                for entries in [leaderboard_top,leaderboard_chunk]
                for (user_id, _) in entries
            )

        if sort_criteria is not None:
            text += ""
        else:
            text += """\n-# Tip: Achieve a better overall score by logging more days and minimizing your total sleep deficit (<8h) and -surplus (>9h, but punished less)."""

        # Send mentions string.
        if mentions_str:
            mentions_msg = await ctx.send(f"({random.choice("🌑🌒🌓🌔🌕🌖🌗🌘🌙🌚🌛🌜🌝")} loading names...)")
            await mentions_msg.edit(content=mentions_str)
            await mentions_msg.delete()

        # Assemble and send embed.
        embed = discord.Embed(
            title=f"Sleeptober Leaderboard 2025 {EMOJIS['bedge']}",
            description=text,
            color=COLORS["low"]
        )
        await ctx.send(embed=embed)

@bot.command(hidden=True)
async def sudo(ctx):
    """[admin cmd] superuser do."""
    if not ctx.message.author.bot and str(ctx.message.author.id) in CONFIG["admin_ids"]:
        exec("a = None\n" + ctx.message.content[len(f"{COMMAND_PREFIX}sudo"):].lstrip(), globals(), globals())
        if a is not None: await ctx.send(a)
    else:
        await ctx.message.reply(f"User is not in the sudoers file. This incident will be reported.", delete_after=60)


@bot.command()
async def zzz(ctx):
    """[admin cmd] Shuts down the bot."""
    # Load user id.
    if ctx.message.author.bot:
        await ctx.message.add_reaction('🤖')
        return
    author_user_id = ctx.message.author.id

    # Needs to be 'admin'.
    if str(author_user_id) not in CONFIG["admin_ids"]:
        await ctx.message.add_reaction('🔐')
        return

    # goodbye
    await ctx.message.add_reaction('💤')
    print(f"[ '{bot.user}' shutting down by admin command. ]")
    await bot.close()

if __name__=="__main__":
    # Ensure data file is ready.
    if not os.path.exists(DATA_FILE):
        store_data({})

    # Load bot config from local file.
    try:
        with open(CONFIG_FILE, 'r') as file:
            CONFIG = json.load(file)
    except:
        raise RuntimeError(f"Attempted to start Sleeptober bot without an available configuration file called `{CONFIG_FILE}`. However, it is required that this file exists, with content the form `{{'token': 'Discord Bot Token Here', 'admin_ids': ['Discord User ID Here', ...]}}`")
    # Start bot.
    bot.run(CONFIG['token'])
