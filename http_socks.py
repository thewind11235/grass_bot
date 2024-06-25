# Copyright © 2024 Mingdv. All rights reserved.

import asyncio
import random
import ssl
import json
import time
import uuid
from loguru import logger
import httpx
import websockets
import socks
import socket

# Directory to store device ID files
DEVICE_ID_DIR = os.path.join(os.getcwd(), "device_id")

# Ensure the directory exists
if not os.path.exists(DEVICE_ID_DIR):
    os.makedirs(DEVICE_ID_DIR)

def get_device_id_file(proxy):
    sanitized_proxy = proxy.replace(":", "_").replace("/", "_").replace("@", "_")
    return os.path.join(DEVICE_ID_DIR, f"device_id_{sanitized_proxy}.txt")

def get_device_id(proxy):
    device_id_file = get_device_id_file(proxy)
    if os.path.exists(device_id_file):
        with open(device_id_file, "r") as file:
            return file.read().strip()
    else:
        device_id = str(uuid.uuid4())
        with open(device_id_file, "w") as file:
            file.write(device_id)
        return device_id

def create_socks_connection(http_proxy):
    proxy_url = http_proxy.replace("http://", "socks5://").replace("https://", "socks5://")
    proxy_host, proxy_port = proxy_url.split('@')[1].split(':')
    proxy_port = int(proxy_port)
    proxy_user, proxy_pass = proxy_url.split('@')[0].replace("socks5://", "").split(':')
    return proxy_host, proxy_port, proxy_user, proxy_pass

async def connect_to_wss(http_proxy, user_id):
    device_id = get_device_id()
    logger.info(device_id)
    while True:
        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            custom_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            }
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            async with httpx.AsyncClient(proxies={"http://": http_proxy, "https://": http_proxy}) as client:
                response = await client.get("http://icanhazip.com")
                logger.info(f"Proxy IP: {response.text.strip()}")

            proxy_host, proxy_port, proxy_user, proxy_pass = create_socks_connection(http_proxy)
            socks.set_default_proxy(socks.SOCKS5, proxy_host, proxy_port, username=proxy_user, password=proxy_pass)
            socket.socket = socks.socksocket

            async with websockets.connect(
                "wss://proxy.wynd.network:4650/",
                ssl=ssl_context,
                extra_headers=custom_headers
            ) as websocket:
                async def send_ping():
                    while True:
                        send_message = json.dumps(
                            {"id": str(uuid.uuid4()), "version": "1.0.0", "action": "PING", "data": {}}
                        )
                        logger.debug(send_message)
                        await websocket.send(send_message)
                        await asyncio.sleep(120)

                await asyncio.sleep(1)
                asyncio.create_task(send_ping())

                while True:
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

        except Exception as e:
            logger.error(e)
            logger.error(http_proxy)

async def main():
    _user_id = '2fFkGwQCG17m9v20ruvyWcPzdv1'

    # Read proxy list from file
    with open('http_socks.txt', 'r') as file:
        http_proxy_list = [line.strip() for line in file.readlines() if line.strip()]

    tasks = [asyncio.ensure_future(connect_to_wss(i, _user_id)) for i in http_proxy_list]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())
