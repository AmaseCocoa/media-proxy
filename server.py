import os
import logging

import aiofiles
import aiohttp
import aiohttp.web as web
from aiohttp_cache import (
    setup_cache,
    cache,
)
from PIL import Image
import io
import urllib.parse

logger = logging.getLogger(__name__)


async def fetch_image(session: aiohttp.ClientSession, url):
    async with session.get(url) as response:
        if not response.ok:
            return None
        else:
            content_type = response.headers.get("Content-Type", "").lower()
            data = bytearray()
            while True:
                chunk = await response.content.read(int(os.environ.get("CHUNK_SIZE", 1048576)))
                if not chunk:
                    break
                data.extend(chunk)
            return data, content_type


@cache(expires=os.environ.get("EXPIRES", 86400) * 1000)
async def proxy_image(request):
    query_params = request.rel_url.query
    url = query_params.get("url")
    fallback = "fallback" in query_params
    emoji = "emoji" in query_params
    avatar = "avatar" in query_params
    static = "static" in query_params
    preview = "preview" in query_params
    badge = "badge" in query_params

    if not url:
        return web.Response(status=400, text="Missing 'url' parameter")

    try:
        url = urllib.parse.unquote(url)
    except Exception as e:
        return web.Response(status=400, text="Invalid 'url' parameter")

    async with aiohttp.ClientSession() as session:
        image_data, content_type = await fetch_image(session, url)

        if image_data is None:
            if fallback:
                headers = {
                    "Cache-Control": "max-age=300",
                    "Content-Type": "image/webp",
                    "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'",
                    "Content-Disposition": "inline; filename=image.webp",
                }
                async with aiofiles.open("./assets/fallback.webp", "rb") as f:
                    return web.Response(
                        status=200, body=await f.read(), headers=headers
                    )
            return web.Response(status=404, text="Image not found")
        if "image" not in content_type:
            logger.info("Media is Not Image. Redirecting to Response...")
            headers = {
                "Cache-Control": "max-age=31536000, immutable",
                "Content-Type": content_type,
                "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'",
                "Content-Disposition": "inline; filename=image.webp",
            }
            return web.Response(status=200, body=image_data, headers=headers)

        image = Image.open(io.BytesIO(image_data))

        if emoji:
            image.thumbnail((128, 128))
        elif avatar:
            image.thumbnail((320, 320))
        elif preview:
            image.thumbnail((200, 200))
        elif badge:
            image = image.convert("RGBA")
            image = image.resize((96, 96))

        output = io.BytesIO()
        image_format = "WEBP" if not badge else "PNG"
        if image_format == "PNG":
            image.save(output, format=image_format, optimize=True)
        elif image_format == "WEBP":
            image.save(output, format=image_format, quality=80)
        output.seek(0)

        headers = {
            "Cache-Control": "max-age=31536000, immutable"
            if image_data
            else "max-age=300",
            "Content-Type": f"image/{image_format.lower()}",
            "Content-Security-Policy": "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'",
            "Content-Disposition": f"inline; filename=image.{image_format.lower()}",
        }

        return web.Response(body=output.read(), headers=headers)


app = web.Application()
setup_cache(app)
app.router.add_get("/proxy/{filename}", proxy_image)

if __name__ == "__main__":
    web.run_app(
        app, port=os.environ.get("PORT", 3003), host=os.environ.get("HOST", "0.0.0.0")
    )
