import io
from urllib.parse import urljoin

from PIL import Image
import numpy as np
import aiohttp
import asyncio

from pai.common import Result, Detail
from .config import API_URI

CHUNK_SIZE = 1024
IMAGE_BASE = 'results'


async def fetch_results():
    url = urljoin(API_URI, '/results')
    print(f'Fetch results: GET {url}')
    async with aiohttp.ClientSession() as session:
        response = await session.get(url)
        data = await response.json()
        response.close()

    return [Result(**x) for x in data]


async def download_image(name, target):
    u = urljoin(API_URI, '/'.join(['images', name, target]))
    print(f'Download image: GET {u}')
    async with aiohttp.ClientSession() as session:
        response = await session.get(u)
        if response.status != 200:
            return None
        stream = io.BytesIO()
        while True:
            chunk = await response.content.read(CHUNK_SIZE)
            if not chunk:
                break
            stream.write(chunk)

        img = Image.open(stream)
        response.close()
        return img

async def fetch_detail(result):
    original_image = await download_image(result.name, result.original)
    overlay_images = []
    for o in result.overlays:
        i = await download_image(result.name, o)
        overlay_images.append(i)
    return Detail(result, original_image, overlay_images)


async def analyze_image(image, name):
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')

    data = aiohttp.FormData()
    data.add_field('name', name)
    data.add_field('image', buffer.getvalue(), filename='image.png', content_type='image/jpeg')

    url = urljoin(API_URI, '/analyze')
    print(f'Analayze image: POST {url}')
    async with aiohttp.ClientSession() as session:
        response = await session.post(url, data=data)
        data = await response.json()
        response.close()

    result = Result(**data)
    return result
