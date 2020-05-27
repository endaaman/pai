import io
from urllib.parse import urljoin
from datetime import datetime

from PIL import Image
import numpy as np
import aiohttp
import asyncio

from .config import API_HOST
from .models import Result

CHUNK_SIZE = 1024


async def download_image(path):
    u = urljoin(API_HOST, path)
    print(f'Get {u}')
    async with aiohttp.ClientSession() as session:
        async with session.get(u) as response:
            if response.status != 200:
                return None
            stream = io.BytesIO()
            while True:
                chunk = await response.content.read(CHUNK_SIZE)
                if not chunk:
                    break
                stream.write(chunk)

            img = Image.open(io.BytesIO(stream.getvalue()))
            return img


async def upload_image(image):
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')

    data = aiohttp.FormData()
    data.add_field('name', datetime.now().strftime("%Y%m%d_%H%M%S"))
    data.add_field('image', buffer.getvalue(), filename='image.jpg', content_type='image/jpeg')

    u = urljoin(API_HOST, '/analyze')
    print(f'Post {u}')
    async with aiohttp.ClientSession() as session:
        async with session.post(u, data=data) as response:
            res = await response.json()

    result = Result(**res)
    print('Result:', result)
    return result
