import io
import cv2
import aiohttp
import asyncio
import numpy as np
from urllib.parse import urljoin


API_HOST = 'http://localhost:8080'
CHUNK_SIZE = 1024

async def download_image(path):
    async with aiohttp.ClientSession() as session:
        u = urljoin(API_HOST, path)
        print(u)
        async with session.get(u) as response:
            if response.status != 200:
                return None
            stream = io.BytesIO()
            while True:
                chunk = await response.content.read(CHUNK_SIZE)
                if not chunk:
                    break
                stream.write(chunk)
            img = cv2.imdecode(np.frombuffer(stream.getvalue(), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            return img
            # return cv2.imdecode(stream.getvalue(), cv2.IMREAD_COLOR)


async def upload_image(mode, image):
    is_success, raw = cv2.imencode('.jpg', image)
    if not is_success:
        print('ERROR')
        return None
    buffer = io.BytesIO(raw)
    data = aiohttp.FormData()
    data.add_field('mode', mode)
    data.add_field('image', buffer.getvalue(), filename='image.jpg', content_type='image/jpeg')
    async with aiohttp.ClientSession() as session:
        async with session.post(urljoin(API_HOST, 'api/analyze'), data=data) as response:
            return await response.json()
