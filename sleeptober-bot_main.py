import discord
from discord.ext import commands
import datetime as dt
import json
import os

# Path to file storing sleep data.
DATA_FILE = "sleeptober-bot_data.json"
# Path to file storing bot token.
CONFIG_FILE = "sleeptober-bot_config.json"

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
* This bot is developed heavily ad-hoc and just for fun :-)"""

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, description=DESCRIPTION, intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')

def store_data(data):
    """Filesystem store global sleep data."""
    with open(DATA_FILE, 'w') as file:
        json.dump(data, file, indent=4)

def load_data():
    """Filesystem load global sleep data."""
    with open(DATA_FILE, 'r') as file:
        data = json.load(file)
    return data

def get_sleeptober_index():
    """Get the index of the currently relevant day (usually yesterday), or None yesterday was not part of October."""
    yesterday = dt.datetime.now() - dt.timedelta(hours=22)
    if yesterday.month == 10:
        return yesterday.day - 1
    else:
        return None

def compute_scoring(user_data):
    """
    Compute some relevant stats from user's raw hours-slept-each-night data:
    - logged_total: Total number of days logged.
    - hours_total: Total number of hours slept.
    - hours_too_few: Total number of hours slept too little each night.
    - hours_too_many: Total number of hours slept too much each night.
    - abstract_score: Abstract score (higher is better)
    """
    logged_total = 0
    hours_total = 0
    hours_squared_total = 0
    hours_too_few = 0
    hours_too_many = 0
    for hours in user_data:
        if hours is not None:
            logged_total += 1
            hours_total += hours
            hours_squared_total += hours**2
            if hours < 8:
                hours_too_few += 8 - hours
            elif 9 < hours:
                hours_too_many += hours - 9
    hours_average = hours_total / (logged_total or 1)
    hours_variance = hours_squared_total / (logged_total or 1) - hours_average ** 2
    abstract_score = 100 * logged_total - hours_too_few - hours_too_many / 2
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
    return (
        logged_total,
        hours_total,
        hours_average,
        hours_variance,
        hours_too_few,
        hours_too_many,
        abstract_score,
    )

def compute_global_leaderboard(data):
    """Generate a a ranked, global leaderboard list."""
    global_leaderboard = sorted(
        ((user_id, compute_scoring(user_data))
            for (user_id, user_data) in data.items()),
        key=lambda t: t[1][-1], # Get abstract_score
        reverse=True # Sort descendingly
    )
    return global_leaderboard

def fmt_hours(hours):
    minutes = round(hours * 60)
    hh = minutes // 60
    mm = minutes % 60
    return f"{hh}:{mm:02}"

def fmt_hours_f(hours):
    return f"{hours:2.2f}"

@bot.command(aliases=["sleep","s",":3"])
async def slept(
        ctx,
        hours_slept: None | str = commands.parameter(description="hours slept, given as a float in the range [0.0, 24.0] or in common `HH:MM` format"),
        night: None | str = commands.parameter(default=None, description="night to manually set, in the range [1, <yesterday>], defaults to last night"),
    ):
    print(f"Hi {hours_slept=} {night=}")
    """Saves how many hours you slept last night."""
    # Compute who is being logged.
    if ctx.message.author.bot:
        await ctx.message.add_reaction('🤖')
        await ctx.message.reply("(Bots cannot participate in Sleeptober (yet))", delete_after=60)
        return
    else:
        user_id = str(ctx.message.author.id)

    # Compute how many hours of sleep are being logged.
    if hours_slept is None:
        await ctx.message.reply("Basic usage:\n- \"I slept a healthy 8.5h last night <:bedge:1176108745865044011>\" -> `>>=slept 8.5`\n- \"Oof! I forgot to log 7h 56min on the night 4th->5th\" -> `>>=slept 7:56 4`")
        return
    else:
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
                (hh,mm) = (int(hh),int(mm))
                if not (0 <= hh < 24 and 0 <= mm < 60 or hh == 24 and mm == 0):
                    raise ValueError
                hours = hh + mm / 60
            except:
                await ctx.message.add_reaction('🙅')
                await ctx.message.reply(f"(That's not a valid time in `HH:MM` or floating point format)", delete_after=60)
                return

    # Compute which day is being logged.
    current_date_index = get_sleeptober_index()
    if night is not None:
        date_cap = current_date_index+1 if current_date_index is not None else 31 # FIXME What if the users queries this *before* October?
        try:
            date = int(night)
            if not (1 <= date <= date_cap):
                raise ValueError
        except:
            await ctx.message.add_reaction('🙅')
            await ctx.message.reply(f"(If you want to specify the night you're logging (second argument) it needs to be an integer in the range [1, {date_cap}])", delete_after=60)
            return
        date_index = date - 1
    else:
        # No day provided by user, default to setting last night's sleep.
        if current_date_index is None:
            await ctx.message.add_reaction('📆')
            await ctx.message.reply("(Last night wasn't part of Sleeptober - check in next year!)", delete_after=60)
            return
        date_index = current_date_index

    # Do the logging.
    # FIXME: There's a data race here where two users can ≈simultaneously write and only one of their infos is stored :wokege:
    data = load_data()
    data.setdefault(user_id, [None for _ in range(31)])[date_index] = hours
    store_data(data)

    # Reaction for visual feedback on success.
    if hours == 0.0:
        await ctx.message.add_reaction('💀')
    elif hours < 6.0:
        await ctx.message.add_reaction("<:wokege:1176108188685324319>")
    else:
        await ctx.message.add_reaction("<:bedge:1176108745865044011>")

@bot.command(aliases=["p"])
async def profile(ctx):
    """Shows how many hours you slept on each day of Sleeptober."""
    async with ctx.typing():
        embed = discord.Embed(
            title="Personal Sleeptober Profile",
            description="",
        )
        # Load user data.
        if ctx.message.author.bot:
            await ctx.message.add_reaction("🤖")
            return
        else:
            user_id = str(ctx.message.author.id)
        data = load_data()
        user_data = data.get(user_id)
        # Generate profile.
        if user_data is None:
            embed.description += "...you haven't slept yet <:wokege:1176108188685324319>\n\nParticipate with `>>=slept`"
        else:
            # Truncate data.
            current_day_index = get_sleeptober_index()
            if current_day_index is None:
                current_day_index = 30 # FIXME What if the users queries this *before* October?
            user_data = user_data[:current_day_index+1]
            # Add ASCII graph.
            (maxwidth_day_index, maxwidth_hours) = (len(str(len(user_data))), 5)
            embed.description += "```c\n"
            embed.description +=  f"{' ': >{maxwidth_day_index}}  {' ': >{maxwidth_hours}} ┍{7*'┯'}┳┳{14*'┯'}┑\n"
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
                embed.description += f"{day_index+1: >{maxwidth_day_index}}. {f'{fmt_hours(hours)}' if hours is not None else '?': >{maxwidth_hours}} {''.join(chars)}\n"
            #embed.description += f"{' ': >{maxwidth_day_index}}  {' ': >{maxwidth_hours}}  ┕{7*'┷'}┷┷{14*'┷'}┙\n"
            embed.description += "```\n"
            # Add value summary.
            (logged_total, hours_total, hours_average, hours_variance, hours_too_few, hours_too_many, abstract_score) = compute_scoring(user_data)
            embed.description += f""" • {logged_total} days logged.
 • Cumulative short of 8h sleep: `-{fmt_hours(hours_too_few)}` h.
 • Cumulative above 9h sleep: `+{fmt_hours(hours_too_many)}` h.
 • Stat. sleep average: `{fmt_hours(hours_average)}` h.
 • Stat. sleep deviation: `{fmt_hours(hours_variance**.5)}` h."""
        await ctx.message.reply(embed=embed)

@bot.command(aliases=["lb"])
async def leaderboard(ctx):
    """Shows the current (global) Sleeptober leaderboard."""
    async with ctx.typing():
        embed = discord.Embed(
            title = "D-INFK Sleeptober 2024 Leaderboard <:bedge:1176108745865044011>",
            description = "",
        )
        data = load_data()
        if not data:
            embed.description += "\n...Feelin' empty :("
        else:
            global_leaderboard_32 = compute_global_leaderboard(data)[:32]
            embed.description += '\n'.join(f"{index+1}. `{f'-{fmt_hours_f(hours_too_few)}': >6} {f'+{fmt_hours_f(hours_too_many)}': >6}`, avg.{fmt_hours_f(hours_total / (logged_total or 1))}h <@{user_id}> ({logged_total}d)" for index, (user_id, (logged_total, hours_total, hours_average, hours_variance, hours_too_few, hours_too_many, abstract_score)) in enumerate(global_leaderboard_32))
        embed.description += """\n\nHigher rank on the leaderboard is awarded by:
- maximizing the number of days you logged,
- minimizing the sum of hours you were short of sleeping 8h each night,
- minimizing the sum of hours above 9h each night."""

        # Make tags load correctly(??) (code inspired by /jackra1n/substiify-v2).
        mentions_msg = await ctx.send("loading ...")
        mentions_str = ''.join(f"<@{user_id}>" for (user_id, _) in global_leaderboard_32)
        await mentions_msg.edit(content=mentions_str)
        await mentions_msg.delete()

        await ctx.send(embed=embed)

@bot.command()
async def shutdown(ctx):
    """[admin] Shuts down the bot."""
    # Load user id.
    if ctx.message.author.bot:
        await ctx.message.add_reaction('🤖')
        return
    else:
        user_id = str(ctx.message.author.id)
    if user_id not in CONFIG['admin_ids']:
        await ctx.message.add_reaction('❌')
        return
    else:
        await ctx.message.add_reaction('✅')
        exit()

if __name__=="__main__":
    # Ensure data file is ready.
    if not os.path.exists(DATA_FILE):
        store_data({})

    # Load bot config from local file.
    with open(CONFIG_FILE, 'r') as file:
        CONFIG = json.load(file)

    # Start bot.
    bot.run(CONFIG['token'])
