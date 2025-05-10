from cryptography.fernet import Fernet
import os
import sys
import json
from typing import Union
from configs.setup_logger import setup_logger

def get_resource_path(relative_path):
    """Resolves path to bundled or script-relative resource"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Updated log file path (logs to same dir as .py or .exe)
log = setup_logger(__name__)

def encrypt(secret_message: str):
    """Returns encrypted secret message"""
    secret_stoken = secret_message.encode()
    key = Fernet.generate_key()
    stoken_key = Fernet(key)
    return key, stoken_key.encrypt(secret_stoken)

def decrypt(key, stoken: str | bytes):
    if not isinstance(stoken, bytes):
        stoken = stoken.encode()
    return Fernet(key).decrypt(stoken).decode("utf-8")

def encrypt_to_config(secret_string: str, name: str, file_path: str = None):
    key_name = f"{name}_key"
    stoken_name = f"{name}_token"
    key, stoken = encrypt(secret_string)
    data = {
        key_name: key.decode('utf-8'),
        stoken_name: stoken.decode('utf-8')
    }

    # Use default file path if not provided
    if file_path is None:
        file_path = get_resource_path("configs/config.json")

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Load or create config
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                config = {}
    else:
        config = {}

    config.update(data)

    try:
        with open(file_path, 'w') as f:
            json.dump(config, f, indent=4)
            log.info(f"SUCCESS: Stored keys in {file_path}")
    except Exception as e:
        log.error(f"ERROR writing to config: {e}")

def decrypt_from_config(name: str, file_path: str = None):
    key_name = f"{name}_key"
    stoken_name = f"{name}_token"

    if file_path is None:
        file_path = get_resource_path("configs/config.json")

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Config file not found at {file_path}")

    with open(file_path, 'r') as f:
        config = json.load(f)

    key = config.get(key_name)
    stoken = config.get(stoken_name)

    if key is None or stoken is None:
        raise KeyError(f"Missing '{key_name}' or '{stoken_name}' in config.")

    return decrypt(key.encode(), stoken)
