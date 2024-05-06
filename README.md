# KlikVoorKamers New Listings Notifier

This Python script checks for new listings on klikvoorkamers.nl and sends notifications through a Telegram bot.

## Features

* Checks for new listings periodically.
* Can be run as a `systemd` service on Linux for background execution and automatic restarts. I run it on my Raspberry Pi.
* Sends Telegram notifications with listing URL, ID and price.
* Configurable through a YAML file.

## Requirements

* Python 3.7+
* Required libraries (install using `pip install -r requirements.txt`):
    * requests
    * python-telegram-bot
    * pyyaml

## Setup

1. **Create a Telegram Bot:**
   - Talk to the BotFather on Telegram and create a new bot.
   - Get the bot token and save it.
2. **Configure `variables.yml`:**
```
chat_ids:
- '12345678'
listings:
- '55555'
tg_token: <telegram_bot_token>
verbosity: debug
```
   - Set `tg_token` to your bot token.
   - Set `chat_ids` to a list of Telegram chat IDs to send notifications to. You can determine the chat IDs by running `test_bot()` after starting the bot in the Telegram app and sending any message to it.
   - Set `verbosity` to the desired logging level (e.g., "DEBUG", "INFO", "WARNING").
   - For now, storing the listings' IDs in the text file should be sufficient for the number of posted ads.
3. **Run the script:**
   - **Manually:** `python main.py`
   - **As a systemd service (Linux):**
     1. Copy the provided `klikvoorkamers.service` file to `/etc/systemd/system/`
     2. **Remember to modify the paths before using it!** Edit the file and replace `<path to>` with the actual path to your script and Python executable.
     3. Reload systemd: `sudo systemctl daemon-reload`
     4. Start the service: `sudo systemctl start klikvoorkamers.service`
     5. (Optional) Enable the service to start automatically on boot: `sudo systemctl enable klikvoorkamers.service`

## Usage

The script will run continuously, checking for new listings every 10 minutes. When a new listing is found, it will send a notification to the specified Telegram chats.

## Logging

Logs are written to a file named `logging.log` in the same directory as the script.
