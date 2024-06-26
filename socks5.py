# -*- coding: utf-8 -*-
# Copyright © 2024 Mingdv. All rights reserved.

import asyncio
import random
import ssl
import json
import time
import aiohttp
from loguru import logger
import websockets
from websockets_proxy import Proxy, proxy_connect
import os
import uuid
import secrets

# Directory to store device ID files
DEVICE_ID_DIR = os.path.join(os.getcwd(), "device_id")

# Ensure the directory exists
if not os.path.exists(DEVICE_ID_DIR):
    os.makedirs(DEVICE_ID_DIR)

# Log file for proxy errors
ERROR_LOG_FILE = os.path.join(os.getcwd(), "grass.log")
logger.add(ERROR_LOG_FILE, level="ERROR")

def uuidv4():
    return (
        '{:08x}-{:04x}-4{:03x}-{:04x}-{:012x}'.format(
            secrets.randbits(32),
            secrets.randbits(16),
            secrets.randbits(12),
            (secrets.randbits(14) | 0x8000) & 0xBFFF,
            secrets.randbits(48)
        )
    )

def get_device_id_file(proxy):
    sanitized_proxy = proxy.replace(":", "_").replace("/", "_").replace("@", "_")
    return os.path.join(DEVICE_ID_DIR, f"device_id_{sanitized_proxy}.txt")

def get_device_id(proxy):
    device_id_file = get_device_id_file(proxy)
    if os.path.exists(device_id_file):
        with open(device_id_file, "r") as file:
            return file.read().strip()
    else:
        device_id = uuidv4()
        with open(device_id_file, "w") as file:
            file.write(device_id)
        return device_id

async def check_internet():
    """Check internet connection by sending a request to a reliable server with retries."""
    retry_delay = 5  # Initial delay between retries
    max_retries = 5  # Maximum number of retries
    retries = 0

    while retries < max_retries:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://www.google.com', timeout=5):
                    return True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            logger.warning(f"Internet check failed. Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
            retries += 1
    return False

async def connect_to_wss(socks5_proxy, user_id):
    device_id = get_device_id(socks5_proxy)
    logger.info(f"Connecting to WebSocket server with device_id: {device_id} and proxy: {socks5_proxy}")

    while True:
        if not await check_internet():
            logger.warning("No internet connection. Waiting to reconnect...")
            await asyncio.sleep(5)
            continue

        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            custom_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
            }
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            uri = "wss://proxy.wynd.network:4650/"
            server_hostname = "proxy.wynd.network"
            proxy = Proxy.from_url(socks5_proxy)
            async with proxy_connect(uri, proxy=proxy, ssl=ssl_context, server_hostname=server_hostname,
                                     extra_headers=custom_headers) as websocket:
                async def send_ping():
                    while True:
                        send_message = json.dumps(
                            {"id": uuidv4(), "version": "1.0.0", "action": "PING", "data": {}})
                        logger.debug(send_message)
                        await websocket.send(send_message)
                        await asyncio.sleep(60)

                await asyncio.sleep(1)
                asyncio.create_task(send_ping())

                while True:
                    if not await check_internet():
                        logger.warning("Internet connection lost. Closing WebSocket connection.")
                        await websocket.close()
                        break

                    try:
                        response = await websocket.recv()
                        message = json.loads(response)
                        logger.info(message)
                        if message.get("action") == "AUTH":
                            auth_response = {
                                "id": message["id"],
                                "origin_action": "AUTH",
                                "result": {
                                    "browser_id": device_id,
                                    "user_id": user_id,
                                    "user_agent": custom_headers['User-Agent'],
                                    "timestamp": int(time.time()),
                                    "device_type": "extension",
                                    "version": "4.20.2",
                                    "extension_id": "lkbnfiajjmbhnfledhphioinpickokdi"
                                }
                            }
                            logger.debug(auth_response)
                            await websocket.send(json.dumps(auth_response))

                        elif message.get("action") == "PONG":
                            pong_response = {"id": message["id"], "origin_action": "PONG"}
                            logger.debug(pong_response)
                            await websocket.send(json.dumps(pong_response))

                    except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as e:
                        logger.warning(f"WebSocket connection closed: {e}")
                        break
                    except asyncio.TimeoutError:
                        logger.warning("Timeout while waiting for WebSocket response. Retrying...")
                        continue

        except websockets.InvalidStatusCode as e:
            error_message = f"WebSocket connection failed with status code: {e.status_code}"
            logger.error(error_message)
            with open(ERROR_LOG_FILE, "a") as error_log:
                error_log.write(f"{error_message}\n")
            if e.status_code == 4000 and "Device creation limit exceeded" in str(e):
                backoff_time = 60  # Initial backoff time in seconds
                while True:
                    logger.warning(f"Device creation limit exceeded. Retrying in {backoff_time} seconds...")
                    await asyncio.sleep(backoff_time)
                    backoff_time = min(backoff_time * 2, 3600)  # Exponential backoff capped at 1 hour
                    if await check_internet():
                        break

        except Exception as e:
            error_message = f"Unexpected error with user_id {user_id} and proxy {socks5_proxy}: {e}"
            logger.error(error_message)
            with open(ERROR_LOG_FILE, "a") as error_log:
                error_log.write(f"{error_message}\n")

        logger.info("Reconnecting to WebSocket server...")
        await asyncio.sleep(5)

async def main():
    _user_id = '2fFkGwQCG17m9v20ruvyWcPzdv1'

    # Read proxy list from file
    with open('socks5_list.txt', 'r') as file:
        socks5_proxy_list = [line.strip() for line in file.readlines() if line.strip()]

    tasks = [asyncio.ensure_future(connect_to_wss(proxy, _user_id)) for proxy in socks5_proxy_list]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())
