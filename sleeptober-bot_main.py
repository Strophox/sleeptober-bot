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
* This bots is developed heavily ad-hoc and just for fun :-)"""

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
    """Compute some relevant stats from user's raw hours-slept-each-night data."""
    # Total number of days logged.
    logged_total = 0
    # Total number of hours slept.
    hours_total = 0
    # Total number of hours slept too little each night.
    hours_too_few = 0
    # Total number of hours slept too much each night.
    hours_too_many = 0
    for hours in user_data:
        if hours is not None:
            logged_total += 1
            hours_total += hours
            if hours < 8:
                hours_too_few += 8 - hours
            elif 9 < hours:
                hours_too_many += hours - 9
    scoring = (logged_total, hours_total / (logged_total or 1), hours_too_few, hours_too_many)
    return scoring

def compute_global_leaderboard(data):
    """Generate a a ranked, global leaderboard list."""
    # Associate scoring to each user.
    global_leaderboard = [(user_id, compute_scoring(user_data)) for (user_id, user_data) in data.items()]

    # Sort leaderboard
    global_leaderboard.sort(key=lambda t: (31 - t[1][0], t[1][2], t[1][3]))
    # (user_id, (logged_total, hours_average, hours_too_few, hours_too_many))

    return global_leaderboard

@bot.command(aliases=["sleep","s"])
async def slept(
        ctx,
        hours_slept: None | str = commands.parameter(description="hours slept, given as a float in the range [0.0, 24.0] or in common `HH:MM` format"),
        day: None | int = commands.parameter(default=None, description="night to manually set, in the range [1, <current day>], defaults to last night"),
    ):
    """Saves how many hours you slept last night."""
    # Compute who is being logged.
    if ctx.message.author.bot:
        await ctx.message.add_reaction('🤖')
        await ctx.message.reply("(Bots cannot participate in Sleeptober (yet))")
        return
    else:
        user_id = str(ctx.message.author.id)

    # Compute how many hours of sleep are being logged.
    if hours_slept is None:
        await ctx.message.reply("Basic usage: E.g. \"I slept a healthy 8.5h last night <:bedge:1176108745865044011>\" -> `>>=slept 8.5`")
        return
    else:
        # Try parsing as float.
        try:
            hours = float(hours_slept)
            if not 0 <= hours <= 24:
                await ctx.message.add_reaction('🙅')
                await ctx.message.reply("(Turns out you can only sleep between [0.0, 24.0]h a day)")
                return
        except Exception:
            # Try parsing as `HH:MM`.
            try:
                [hh,mm] = hours_slept.split(':')
                (hh,mm) = (int(hh),int(mm))
                if not (0 <= hh <= 24 and 0 <= mm <= 60) or (hh == 24 and mm != 0):
                    raise Exception
                hours = hh + mm / 60
            except Exception:
                await ctx.message.add_reaction('🙅')
                await ctx.message.reply(f"('{hours_slept}' is not a valid time in `HH:MM` format)")
                return

    # Compute which day is being logged.
    current_day_index = get_sleeptober_index()
    if day is not None:
        day_cap = current_day_index+1 if current_day_index is not None else 31 # FIXME What if the users queries this *before* October?
        if not 1 <= day <= day_cap:
            await ctx.message.add_reaction('🙅')
            await ctx.message.reply(f"(The night whose value you want to manually set needs to be in the range [1, {day_cap}])")
            return
        else:
            day_index = day - 1
    else:
        # No day provided by user, default to setting last night's sleep.
        if current_day_index is None:
            await ctx.message.add_reaction('📆')
            await ctx.message.reply("(Last night wasn't part of Sleeptober)")
            return
        else:
            day_index = current_day_index

    # Do the logging.
    # FIXME: There's a data race here where two users can ≈simultaneously write and only one of their infos is stored :wokege:
    data = load_data()
    data.setdefault(user_id, [None for _ in range(31)])[day_index] = hours
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
        data = load_data()
        if not data:
            embed.description += "...you haven't slept yet <:wokege:1176108188685324319>\n\nParticipate with `>>=slept`"
        else:
            # Load user data.
            if ctx.message.author.bot:
                await ctx.message.add_reaction("🤖")
                return
            else:
                user_id = str(ctx.message.author.id)
            current_day_index = get_sleeptober_index()
            if current_day_index is None:
                current_day_index = 30 # FIXME What if the users queries this *before* October?
            user_data = data[user_id][:current_day_index+1]

            # Prepare ASCII graph.
            (maxwidth_day_index, maxwidth_hours) = (len(str(len(user_data))), len(str(max(f"{hours:2.2f}" for hours in user_data if hours is not None))))
            embed.description += "```c\n"
            embed.description +=  f"{' ': >{maxwidth_day_index}}  {' ': >{maxwidth_hours}}  ┍{7*'┯'}┯┯{14*'┯'}┑\n"
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
                embed.description += f"{day_index+1: >{maxwidth_day_index}}. {f'{hours:2.2f}' if hours is not None else '?': <{maxwidth_hours}}h {''.join(chars)}\n"
            #embed.description += f"{' ': >{maxwidth_day_index}}  {' ': >{maxwidth_hours}}  ┕{7*'┷'}┷┷{14*'┷'}┙\n"
            embed.description += "```\n"
            (logged_total, hours_average, hours_too_few, hours_too_many) = compute_scoring(user_data)
            embed.description += f"{logged_total} days logged.\n"
            embed.description += f"Cumulative hours short of 8h sleep: `-{hours_too_few:2.2f}`.\n"
            embed.description += f"Cumulative hours above 9h sleep: `+{hours_too_many:2.2f}`.\n"
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
            embed.description += '\n'.join(f"{index+1}. `{f'-{hours_too_few:2.2f}': >6} {f'+{hours_too_many:2.2f}': >6}`, avg.{hours_average:.02f}h <@{user_id}> ({logged_total}d)" for index, (user_id, (logged_total, hours_average, hours_too_few, hours_too_many)) in enumerate(global_leaderboard_32))
        embed.description += """\n\nHigher rank on the leaderboard is awarded by:
- maximizing the number of days you logged,
- minimizing the sum of hours you were short of sleeping 8h each night,
- minimizing the sum of hours above 9h each night."""

        # Make tags load correctly(??) (code inspired by /jackra1n/substiify-v2).
        mentions_msg = await ctx.send("loading...")
        mentions_str = ''.join(f"<@{user_id}>" for (user_id, _) in global_leaderboard_32)
        await mentions_msg.edit(content=mentions_str)
        await mentions_msg.delete()

        await ctx.send(embed=embed)

@bot.command()
async def shutdown(ctx):
    """['admin'] Shuts bot down."""
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
        await ctx.message.add_reaction("<:bedge:1176108745865044011>")
        exit()

if __name__=="__main__":
    # Ensure data file is ready.
    if not os.path.exists(DATA_FILE):
        store_data({})

    # Load bot token from local file.
    with open(CONFIG_FILE, 'r') as file:
        CONFIG = json.load(file)

    # Start bot.
    bot.run(CONFIG['token'])
