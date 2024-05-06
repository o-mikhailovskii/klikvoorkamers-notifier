import asyncio
import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Set
from urllib.parse import parse_qs, urlparse

import requests
import telegram
import yaml

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set default logging level

# Constants
USER_AGENT = """Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) \
AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15"""
LISTINGS_URL = "https://www.klikvoorkamers.nl/en/offerings/now-for-rent/rooms/studios"

PORTAL_URL_BASE = "https://www.klikvoorkamers.nl/portal"
JSON_FRONTEND_URL_BASE = f"{PORTAL_URL_BASE}/object/frontend"
LISTINGS_API_URL = f"{JSON_FRONTEND_URL_BASE}/getallobjects/format/json"

LOGIN_HASH_ID_URL = (
    f"{PORTAL_URL_BASE}/account/frontend/getloginconfiguration/format/json"
)
LOGIN_URL = f"{PORTAL_URL_BASE}/account/frontend/loginbyservice/format/json"
login_load = {
    "__id__": "Account_Form_LoginFrontend",
}

REACTION_HASH_ID_URL = f"{PORTAL_URL_BASE}/core/frontend/\
getformsubmitonlyconfiguration/format/json"
LISTING_DETAILS_URL = f"{JSON_FRONTEND_URL_BASE}/getobject/format/json"
REACTION_URL = f"{JSON_FRONTEND_URL_BASE}/react/format/json"


def setup_logging(verbosity: str):
    """
    Configures logging settings.

    Args:
        verbosity: The desired logging level (e.g., "DEBUG", "INFO", "WARNING").
    """
    # Create file handler with rotating log files
    file_handler = RotatingFileHandler(Path(__file__).resolve().parent / "logging.log")
    # Create formatter and add it to the handler
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    # Add file handler to the logger
    logger.addHandler(file_handler)
    # Set logging level from config
    logger.setLevel(verbosity)


async def send_telegram_notification(
    new_listing: dict, tg_token: str, chat_ids: List[str]
):
    """
    Sends a Telegram notification about a new listing.

    Args:
        new_listing: The new listing JSON.
        tg_token: The Telegram bot token.
        chat_ids: A list of chat IDs to receive the notification.
    """
    bot = telegram.Bot(token=tg_token)
    # Prepare the message
    new_listing_id = new_listing["id"]
    new_listing_url = f'{LISTINGS_URL}/details/{new_listing["urlKey"]}'
    message = (
        f"New listing available at {new_listing_url}\n"
        f"ID: {new_listing_id}\n"
        f"Price: {new_listing['totalRent']}"
    )
    async with bot:
        # Send the message to recipients
        for chat_id in chat_ids:
            try:
                await bot.send_message(chat_id=chat_id, text=message)
                logger.info(f"Notification sent for listing ID: {new_listing_id}")
            except telegram.error.TelegramError as e:
                logger.error(f"Error sending notification: {e}")


def apply_for_new_listing(session: requests.Session, listing):
    """
    Applies for a new listing.

    Args:
        session: The requests session object.
        listing: The listing JSON object.
    """
    listing_id = listing["id"]
    try:
        # Get listing details
        response = session.post(LISTING_DETAILS_URL, data={"id": listing["id"]})
        response.raise_for_status()
        reaction_data = response.json()["result"]["reactionData"]
        action = reaction_data["action"]

        # Apply for the listing
        if action == "add":
            add_id = reaction_data["url"]
            response = session.get(REACTION_HASH_ID_URL)
            response.raise_for_status()
            reaction_load = {
                "__id__": "Portal_Form_SubmitOnly",
                "__hash__": response.json()["form"]["elements"]["__hash__"][
                    "initialData"
                ],
                "dwellingID": int(parse_qs(urlparse(add_id).query)["dwellingID"][0]),
                action: int(parse_qs(urlparse(add_id).query)[action][0]),
            }
            response = session.post(REACTION_URL, data=reaction_load)
            response.raise_for_status()
            if response.json()["success"]:
                logger.info(f"Successfully applied: {listing_id}")
                logger.debug(response.json()["reactionData"])
            else:
                logger.warning(f"Something went wrong: {listing_id}")

        else:
            logger.info(f"Already applied? {listing_id}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error applying for listing {listing_id}: {e}")


def check_for_new_listings(
    session: requests.Session,
    known_listings: Set[str],
    tg_token: str,
    chat_ids: List[str],
) -> Set[str]:
    """
    Checks for new listings and sends notifications if any are found.

    Args:
        session: The requests session object.
        known_listings: A set of known listing IDs.
        tg_token: The Telegram bot token.
        chat_ids: A list of chat IDs to receive notifications.

    Returns:
        The updated set of known listing IDs.
    """
    try:
        # Get the page to "trick" anti-spam filter
        response = session.get(LISTINGS_URL)
        response.raise_for_status()
        session.headers.update({"referer": LISTINGS_URL})

        # Get the current listings
        response = session.get(LISTINGS_API_URL)
        response.raise_for_status()
        listings_data = response.json()["result"]
        listings_to_apply = []

        for listing in listings_data:
            listing_id = listing["id"]
            # Form persistent list of ids and of those which to apply for
            if listing_id not in known_listings:
                listings_to_apply.append(listing)
                known_listings.add(listing_id)
                logger.info(f"New listing found: {listing_id}")

        if len(listings_to_apply) > 0:
            # Login to apply
            response = session.get(LOGIN_HASH_ID_URL)
            response.raise_for_status()
            login_load["__hash__"] = response.json()["loginForm"]["elements"][
                "__hash__"
            ]["initialData"]
            response = session.post(LOGIN_URL, data=login_load)
            response.raise_for_status()
            if not response.json()["loggedIn"]:
                logger.warning(f"Could not login: {response.json()}")
            else:
                for listing in listings_to_apply:
                    apply_for_new_listing(session, listing)
                    asyncio.run(
                        send_telegram_notification(
                            listing,
                            tg_token,
                            chat_ids,
                        )
                    )

    except requests.exceptions.RequestException as e:
        logger.error(f"Error checking for new listings: {e}")

    return known_listings


async def test_bot(tg_token: str) -> List[int]:
    """
    Tests the Telegram bot connection and retrieves the chat IDs of users who have
    sent a message to the bot.

    Args:
        tg_token (str): The Telegram bot token.

    Returns:
        List[int]: A list of chat IDs of users who have sent a message to the bot.

    Raises:
        KeyError: If the chat ID could not be extracted from the Telegram update.

    Notes:
        - This function requires the bot to be started in the Telegram app.
        - Users must send a message to the bot for their chat ID to be retrieved.
        - The function will print the bot's details (using `bot.get_me()`) before
          retrieving the chat IDs.
    """
    bot = telegram.Bot(token=tg_token)
    result = []
    async with bot:
        print(await bot.get_me())
        updates = await bot.get_updates()
        for update in updates:
            try:
                chat_id = update["message"]["chat"]["id"]
                result.append(chat_id)
            except KeyError:
                logging.error("Could not extract chat_id's to send notifications")
    return result


if __name__ == "__main__":
    # Read settings and variables
    with open("variables.yml", "r") as file:
        settings = yaml.safe_load(file)
        known_listings = set(settings["listings"])
        tg_token = settings["tg_token"]
        chat_ids = settings["chat_ids"]
        setup_logging(settings["verbosity"].upper())
        login_load["username"] = settings["login"]
        login_load["password"] = settings["password"]

    # Create a `Session()` since the website requires to keep cookies
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Determine chat_id's to send notifications based on requests to the bot
    if not chat_ids:
        chat_ids = asyncio.run(test_bot(tg_token))
        settings["chat_ids"] = chat_ids

    # Check and apply for new listings every 10 minutes
    while True:
        # Check for new listings
        known_listings = check_for_new_listings(
            session, known_listings, tg_token, chat_ids
        )
        settings["listings"] = list(known_listings)
        with open("variables.yml", "w") as file:
            yaml.dump(settings, file)
        time.sleep(600)  # Check every 10 minutes
