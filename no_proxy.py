# Copyright © 2024 Mingdv. All rights reserved.

import asyncio
import random
import ssl
import json
import time
import uuid
import aiohttp
import websockets
from loguru import logger
import os

# Đường dẫn thư mục lưu trữ thông tin
STORAGE_DIR = "user_data"

# Tạo thư mục lưu trữ nếu chưa tồn tại
if not os.path.exists(STORAGE_DIR):
    os.makedirs(STORAGE_DIR)

def get_device_id(user_id):
    device_id_file = os.path.join(STORAGE_DIR, f"{user_id}_device_id.txt")
    if os.path.exists(device_id_file):
        with open(device_id_file, 'r') as file:
            return file.read().strip()
    else:
        device_id = str(uuid.uuid4())
        with open(device_id_file, 'w') as file:
            file.write(device_id)
        return device_id

def save_session_info(session_info, user_id):
    session_info_file = os.path.join(STORAGE_DIR, f"{user_id}_session_info.json")
    with open(session_info_file, 'w') as file:
        json.dump(session_info, file)

def load_session_info(user_id):
    session_info_file = os.path.join(STORAGE_DIR, f"{user_id}_session_info.json")
    if os.path.exists(session_info_file):
        with open(session_info_file, 'r') as file:
            return json.load(file)
    return None

async def check_internet():
    retry_delay = 5
    max_retries = 5
    retries = 0

    while retries < max_retries:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://www.google.com', timeout=5):
                    return True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            logger.warning(f"Internet check failed. Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2
            retries += 1
    return False

async def connect_to_wss(user_id, semaphore):
    async with semaphore:
        device_id = get_device_id(user_id)
        logger.info(f"Device ID for user {user_id}: {device_id}")
        session_info = load_session_info(user_id)

        while True:
            if not await check_internet():
                logger.warning("No internet connection. Waiting to reconnect...")
                await asyncio.sleep(5)
                continue

            try:
                await asyncio.sleep(random.randint(1, 10) / 10)
                custom_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
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
                            await asyncio.sleep(120)

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
                                if session_info and session_info.get("token"):
                                    auth_response = {
                                        "id": message["id"],
                                        "origin_action": "AUTH",
                                        "result": {
                                            "token": session_info["token"],
                                            "device_id": device_id,
                                            "user_id": user_id,
                                            "user_agent": custom_headers['User-Agent'],
                                            "timestamp": int(time.time()),
                                            "device_type": "extension",
                                            "version": "4.20.2",
                                            "extension_id": "lkbnfiajjmbhnfledhphioinpickokdi"
                                        }
                                    }
                                else:
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

                            elif message.get("action") == "AUTH_SUCCESS":
                                token = message["result"]["token"]
                                session_info = {"token": token}
                                save_session_info(session_info, user_id)

                        except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as e:
                            logger.warning(f"WebSocket connection closed: {e}")
                            break
                        except asyncio.TimeoutError:
                            logger.warning("Timeout while waiting for WebSocket response. Retrying...")
                            continue

            except websockets.InvalidStatusCode as e:
                logger.error(f"WebSocket connection failed with status code: {e.status_code}")
                if e.status_code == 4000 and "Device creation limit exceeded" in str(e):
                    backoff_time = 60
                    while True:
                        logger.warning(f"Device creation limit exceeded. Retrying in {backoff_time} seconds...")
                        await asyncio.sleep(backoff_time)
                        backoff_time = min(backoff_time * 2, 3600)
                        if await check_internet():
                            break

            except Exception as e:
                logger.error(f"Unexpected error: {e}")

            logger.info("Reconnecting to WebSocket server...")
            await asyncio.sleep(5)

async def main():
    user_ids = [
        '2fFkGwQCG17m9v20ruvyWcPzdv1',
        '2iEljtSdvLVJi6d5cNau0ZigeqX',
        '2iFMo3mdOlmm523pn0F4F6U5bsm',
        '2iFN7YqHIrLfSL8gFJXgNvv5PAw',
        '2iFNJAvQaeaCXQvbBipRsq9KoFb',
        '2iFNSO72PMKSRuKoISvU2JPnmLB',
        '2iFNjifOmkwyAMKrahywifpHBvf',
        '2iFNsFtrRNWkjgEBGpjCvyCZbWN',
        '2iFO1GQbp33mKFcEYGnB7Hf4Oxt',
        '2iFO9qhAHxajcH5KLWVoUuMCU6x',
        '2iFONSZeCi85foRPtMnUvNo4ZgX'
    ]

    # Giới hạn số lượng kết nối đồng thời
    max_concurrent_connections = 1
    semaphore = asyncio.Semaphore(max_concurrent_connections)

    await asyncio.gather(*(connect_to_wss(user_id, semaphore) for user_id in user_ids))

if __name__ == '__main__':
    asyncio.run(main())
