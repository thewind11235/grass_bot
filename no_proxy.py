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
        except aiohttp.ClientError:
            logger.warning(f"Internet check failed. Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
            retries += 1
    return False

async def connect_to_wss(user_id):
    device_id = str(uuid.uuid4())
    logger.info(device_id)

    while True:
        if not await check_internet():
            logger.warning("No internet connection. Waiting to reconnect...")
            await asyncio.sleep(5)
            continue

        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            custom_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
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
                                "version": "2.5.0"
                            }
                        }
                        logger.debug(auth_response)
                        await websocket.send(json.dumps(auth_response))

                    elif message.get("action") == "PONG":
                        pong_response = {"id": message["id"], "origin_action": "PONG"}
                        logger.debug(pong_response)
                        await websocket.send(json.dumps(pong_response))

        except websockets.ConnectionClosedError as e:
            logger.error(f"WebSocket connection closed: {e}")
            if "Device creation limit exceeded" in str(e):
                # Exponential backoff strategy for handling the device limit exceeded error
                backoff_time = 60  # Initial backoff time in seconds
                while True:
                    logger.warning(f"Device creation limit exceeded. Retrying in {backoff_time} seconds...")
                    await asyncio.sleep(backoff_time)
                    backoff_time *= 2
                    if backoff_time > 3600:  # Cap the backoff time at 1 hour
                        backoff_time = 3600
                    if await check_internet():
                        break

        except Exception as e:
            logger.error(e)

        logger.info("Reconnecting to WebSocket server...")
        await asyncio.sleep(5)

async def main():
    # TODO 修改user_id
    _user_id = '2fFkGwQCG17m9v20ruvyWcPzdv1'
    await connect_to_wss(_user_id)

if __name__ == '__main__':
    # 运行主函数
    asyncio.run(main())
