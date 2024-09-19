import asyncio
import io
import logging
import os
import platform
import traceback
import urllib.parse

import aiofiles
import aiosonic
import pyvips
from aiohttp.web import Application, Response, run_app
from aiohttp_cache import cache, setup_cache
from aiosonic import HTTPClient
from aiosonic.exceptions import HttpParsingError
from aiosonic.resolver import AsyncResolver

ostype = platform.system()
if ostype == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except ModuleNotFoundError:
        pass

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", 5242880))
EXPIRES = int(os.environ.get("EXPIRES", 86400)) * 1000
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = 3004
version = "0.1.0"


async def fetch_image(client: HTTPClient, url: str):
    try:
        response = await client.get(
            url,
            headers={"User-Agent": f"media-proxy-py/{version}"},
            timeouts=aiosonic.Timeouts(
                sock_connect=10, sock_read=60, request_timeout=120
            ),
        )
        if response.status_code != 200:
            return None, None
        content_type = response.headers.get("Content-Type", "").lower()
        return await response.content(), content_type
    except HttpParsingError as e:
        print(traceback.format_exc())
        return None, None


def process_image(image, emoji, avatar, preview, badge, split_rows=1, split_cols=1):
    # 画像を縮小してメモリ使用量を抑える
    max_size = 2048
    if image.width > max_size or image.height > max_size:
        scale = min(max_size / image.width, max_size / image.height)
        image = image.resize(scale)

    if split_rows > 1 or split_cols > 1:
        return split_image(image, split_rows, split_cols)

    if emoji:
        image = image.thumbnail_image(128)
    elif avatar:
        image = image.thumbnail_image(320)
    elif preview:
        image = image.thumbnail_image(200)
    elif badge:
        image = image.resize(96 / max(image.width, image.height))
    return [image]


def split_image(image, rows, cols):
    width = image.width
    height = image.height
    tile_width = width // cols
    tile_height = height // rows

    tiles = []
    for row in range(rows):
        for col in range(cols):
            left = col * tile_width
            top = row * tile_height
            right = left + tile_width
            bottom = top + tile_height
            tile = image.crop(left, top, tile_width, tile_height)
            tiles.append(tile)

    return tiles


@cache(expires=EXPIRES)
async def proxy_image(request):
    query_params = request.rel_url.query
    url = query_params.get("url")
    fallback = "fallback" in query_params
    emoji = "emoji" in query_params
    avatar = "avatar" in query_params
    static = "static" in query_params
    preview = "preview" in query_params
    badge = "badge" in query_params
    split_rows = int(query_params.get("rows", 1))
    split_cols = int(query_params.get("cols", 1))

    if not url:
        return Response(status=400, text="Missing 'url' parameter")

    try:
        url = urllib.parse.unquote(url)
    except Exception:
        return Response(status=400, text="Invalid 'url' parameter")

    try:
        resolver = AsyncResolver(nameservers=["1.1.1.1", "1.0.0.1"])
        connector = aiosonic.TCPConnector(resolver=resolver)
        async with HTTPClient(connector=connector) as client:
            image_data, content_type = await fetch_image(client, url)

            if image_data is None:
                if fallback:
                    return await fallback_response()
                print("No Image")
                return Response(status=404, text="Image not found")

            if "image" not in content_type:
                return non_image_response(image_data, content_type)

            image = pyvips.Image.new_from_buffer(image_data, "", access="sequential")
            images = process_image(
                image, emoji, avatar, preview, badge, split_rows, split_cols
            )

            output = io.BytesIO()
            image_format = "webp" if not badge else "png"

            # 複数の画像を保存する場合
            for i, img in enumerate(images):
                img_output = io.BytesIO()
                save_image(img, img_output, image_format)
                img_output.seek(0)
                headers = create_headers(image_format, img_output.getvalue())
                return Response(body=img_output.read(), headers=headers)

    except Exception as e:
        print(f"Error processing image: {traceback.format_exc()}")
        if fallback:
            return await fallback_response()
        return Response(status=404, text="Internal Server Error")


def save_image(image, output, image_format):
    buffer = image.write_to_buffer(
        f".{image_format}", Q=80 if image_format == "webp" else None
    )
    output.write(buffer)


def create_headers(image_format, image_data):
    return {
        "Cache-Control": "max-age=31536000, immutable" if image_data else "max-age=300",
        "Content-Type": f"image/{image_format}",
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'",
        "Content-Disposition": f"inline; filename=image.{image_format}",
    }


async def fallback_response():
    headers = {
        "Cache-Control": "max-age=300",
        "Content-Type": "image/webp",
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'",
        "Content-Disposition": "inline; filename=image.webp",
    }
    async with aiofiles.open("./assets/fallback.webp", "rb") as f:
        return Response(status=200, body=await f.read(), headers=headers)


def non_image_response(image_data, content_type):
    headers = {
        "Cache-Control": "max-age=31536000, immutable",
        "Content-Type": content_type,
        "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'",
        "Content-Disposition": "inline; filename=image.webp",
    }
    return Response(status=200, body=image_data, headers=headers)


app = Application()
setup_cache(app)
app.router.add_get("/proxy/{filename}", proxy_image)
app.router.add_get("/", proxy_image)
app.router.add_get("/{filename}", proxy_image)

if __name__ == "__main__":
    run_app(app, port=PORT, host=HOST)
