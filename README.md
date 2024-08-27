# media-proxy
An alternative implementation of Media Proxy created in Python, using aiohttp.web and Pillow.

If you want to change the port or host parameters, change the `PORT` and `HOST` environment variables.
## How To Run
```
docker run -d --name media-proxy -p 3003:3003 amasecocoa/media-proxy
```