# -*- coding: utf-8 -*-
# @Time     :2023/12/26 18:08
# @Author   :mingdv
# @File     :no_proxy.py
# @Software :PyCharm

import asyncio
import random
import ssl
import json
import time
import uuid
import aiohttp

import websockets
from loguru import logger
import winreg

REGISTRY_KEY = r"Software\MyApp"
REGISTRY_VALUE = "device_id"

def get_device_id():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_READ) as key:
            device_id, _ = winreg.QueryValueEx(key, REGISTRY_VALUE)
            return device_id
    except FileNotFoundError:
        device_id = str(uuid.uuid4())
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
            winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, device_id)
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

async def connect_to_wss(user_id):
    device_id = get_device_id()
    logger.info(device_id)

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
            async with websockets.connect(uri, ssl=ssl_context, extra_headers=custom_headers,
                                          server_hostname=server_hostname) as websocket:
                async def send_ping():
                    while True:
                        send_message = json.dumps(
                            {"id": str(uuid.uuid4()), "version": "1.0.0", "action": "PING", "data": {}})
                        logger.debug(send_message)
                        await websocket.send(send_message)
                        await asyncio.sleep(20)

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
            logger.error(f"WebSocket connection failed with status code: {e.status_code}")
            if e.status_code == 4000 and "Device creation limit exceeded" in str(e):
                backoff_time = 60  # Initial backoff time in seconds
                while True:
                    logger.warning(f"Device creation limit exceeded. Retrying in {backoff_time} seconds...")
                    await asyncio.sleep(backoff_time)
                    backoff_time = min(backoff_time * 2, 3600)  # Exponential backoff capped at 1 hour
                    if await check_internet():
                        break

        except Exception as e:
            logger.error(f"Unexpected error: {e}")

        logger.info("Reconnecting to WebSocket server...")
        await asyncio.sleep(5)

async def main():
    _user_id = '2fFkGwQCG17m9v20ruvyWcPzdv1'
    await connect_to_wss(_user_id)

if __name__ == '__main__':
    asyncio.run(main())
