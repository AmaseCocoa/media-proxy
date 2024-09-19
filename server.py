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
import yaml
from aiohttp import web
from aiohttp.web import Application, Response, run_app
from aiohttp_cache import cache, setup_cache
from aiosonic import HTTPClient, Proxy
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
PORT = int(os.environ.get("PORT", 3003))
version = "0.1.0"

with open("./config.yml", "r") as f:
    config = yaml.safe_load(f)
    if config["disguise"]["enable"]:
        server = config["disguise"]["value"]
    else:
        if config["hide_proxy_version"]:
            server = "media-proxy-py"
        else:
            server = f"media-proxy-py/{version}"

async def middleware(app, handler):
    async def middleware_handler(request):
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            raise exc
        if not response.prepared:
            response.headers["Server"] = server
        return response

    return middleware_handler


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
        content = await response.content()
        content_type = response.headers.get("Content-Type", "").lower()
        return content, content_type
    except HttpParsingError:
        print(traceback.format_exc())
        return None, None


def process_image(image, emoji, avatar, preview, badge, split_rows=1, split_cols=1):
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
        if config["dns"]["external"]:
            resolver = AsyncResolver(nameservers=config["dns"]["servers"])
            connector = aiosonic.TCPConnector(resolver=resolver)
        else:
            connector = None
        if config["proxy"]["use"]:
            proxy = Proxy(host=f"{config["proxy"]["type"]}://{config["proxy"]["host"]}{f":{config["proxy"]["port"]}" if config["proxy"]["port"] != "" else ""}", auth=config["proxy"]["auth"] if config["proxy"]["auth"] != "" else None)
        else:
            proxy = None
        async with HTTPClient(connector=connector, proxy=proxy) as client:
            image_data, content_type = await fetch_image(client, url)
            if image_data is None:
                if fallback:
                    return await fallback_response()
                return Response(status=404, text="Image not found")

            is_heif = image_data.startswith(b'\x00\x00\x00\x18ftypheic') or image_data.startswith(b'\x00\x00\x00\x1cftypheic')

            if not config["process_heif"]:
                if content_type in ["image/avif", "image/heif"] or image_data.startswith(b"\x00\x00\x00 ftypavif") or image_data.startswith(b"\x00\x00\x00 ftypheic"):
                    return Response(body=image_data, content_type=content_type)
            elif content_type == "image/gif" or image_data.startswith(b"GIF"):
                return Response(body=image_data, content_type="image/gif")

            if "image" not in content_type:
                return non_image_response(image_data, content_type)

            image = pyvips.Image.new_from_buffer(
                image_data, "", access="sequential", n=-1
            )
            images = process_image(
                image, emoji, avatar, preview, badge, split_rows, split_cols
            )

            output = io.BytesIO()
            image_format = "webp" if not badge else "png"
            for i, img in enumerate(images):
                img_output = io.BytesIO()
                save_image(img, img_output, image_format)
                img_output.seek(0)
                headers = create_headers(image_format, img_output.getvalue())
                return Response(body=img_output.read(), headers=headers)

    except Exception as e:
        if e.__class__ == pyvips.error.Error:
            return Response(body=image_data, content_type=content_type)
        print(f"Error processing image: {traceback.format_exc()}")
        if fallback:
            return await fallback_response()
        return Response(status=500, text="Internal Server Error")


def save_image(image: pyvips.Image, output, image_format):
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
app.middlewares.append(middleware)
app.router.add_get("/proxy/{filename}", proxy_image)
app.router.add_get("/", proxy_image)
app.router.add_get("/{filename}", proxy_image)

if __name__ == "__main__":
    run_app(app, port=PORT, host=HOST)
