import os
import json
import shutil
import datetime
import logging
import aiofiles
from dotenv import load_dotenv
import glob

load_dotenv()

WHITELIST_FILE = "whitelist.txt"
HISTORY_DIR = "user_histories"
AUTH_CODE = os.getenv("AUTH_CODE")

logger = logging.getLogger(__name__)

if not AUTH_CODE:
    raise ValueError("AUTH_CODE is not set in the environment variables. Please check your .env file.")

def is_authenticated(user_id):
    if not os.path.exists(WHITELIST_FILE):
        return False
    with open(WHITELIST_FILE, "r") as f:
        return str(user_id) in f.read().splitlines()

def authenticate_user(user_id):
    with open(WHITELIST_FILE, "a") as f:
        f.write(f"{user_id}\n")

async def save_user_history(user_id, messages, scenario):
    try:
        if not os.path.exists(HISTORY_DIR):
            os.makedirs(HISTORY_DIR)
        async with aiofiles.open(f"{HISTORY_DIR}/{user_id}_{scenario}_history.json", "w") as f:
            await f.write(json.dumps(messages, indent=2))
        logger.info(f"Successfully saved history for user {user_id} in scenario {scenario}")
    except Exception as e:
        logger.error(f"Error saving history for user {user_id} in scenario {scenario}: {str(e)}")

def load_user_history(user_id, scenario):
    history_file = f"{HISTORY_DIR}/{user_id}_{scenario}_history.json"
    if not os.path.exists(history_file):
        return []
    with open(history_file, "r") as f:
        return json.load(f)

def save_user_scenario(user_id, scenario):
    if not os.path.exists(HISTORY_DIR):
        os.makedirs(HISTORY_DIR)
    with open(f"{HISTORY_DIR}/{user_id}_scenario.txt", "w") as f:
        f.write(scenario)

def load_user_scenario(user_id):
    scenario_file = f"{HISTORY_DIR}/{user_id}_scenario.txt"
    if not os.path.exists(scenario_file):
        return 'boyfriend'  # Default scenario
    with open(scenario_file, "r") as f:
        return f.read().strip()

def clear_user_history(user_id, scenario):
    archive_user_history(user_id, scenario)
    with open(f"{HISTORY_DIR}/{user_id}_{scenario}_history.json", "w") as f:
        json.dump([], f)

def archive_user_history(user_id, scenario):
    if not os.path.exists("archive"):
        os.makedirs("archive")

    history_file = f"{HISTORY_DIR}/{user_id}_{scenario}_history.json"
    if os.path.exists(history_file):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = f"archive/{user_id}_{scenario}_history_{timestamp}.json"
        shutil.move(history_file, archive_file)

def is_new_user(user_id):
    user_history_files = glob.glob(f"{HISTORY_DIR}/{user_id}_*_history.json")
    return len(user_history_files) == 0