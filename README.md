#  Sleeptober Discord Bot

This repo hosts the source for a Discord bot made to handle logging sleeping habits for Sleeptober.

## How to run

```bash
# Makes a new virtual environment.
python3 -m venv sleeptober-bot_venv
# Enters virtual environment.
source sleeptober-bot_venv/bin/activate
# Installs discord.py dependency.
pip install discord
# Starts bot (requires sleeptober-bot_token.txt).
python3 sleeptober-bot_main.py
```


# Sleeptober

> Sleeptober was created as a challenge to improve one's sleeping skills and develop positive sleeping habits.

![Sleeptober 2024 Official Prompt List](Gallery/Sleeptober_2024_Official_Prompt_List.png)

*This bots is developed heavily ad-hoc and just for fun :-)


# Additional Notes

- A file `sleeptober-bot_config.json` containing the Discord bot token in plain text is required.
- A file `sleeptober-bot_data.json` containing bot data will be automatically created if it doesn't exist.
