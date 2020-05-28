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
IMAGE_BASE = 'results'


async def download_image(name, target):
    u = urljoin(API_HOST, '/'.join(['results', name, target]))
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


async def analyze_image(image, name):
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')

    data = aiohttp.FormData()
    data.add_field('name', name)
    data.add_field('image', buffer.getvalue(), filename='image.jpg', content_type='image/jpeg')

    u = urljoin(API_HOST, '/analyze')
    print(f'Post {u}')
    async with aiohttp.ClientSession() as session:
        response = await session.post(u, data=data)
        data = await response.json()

    result = Result(**data)
    print('Result:', result)
    return result
