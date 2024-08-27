# Media-Proxy
Media-Proxy is a lightweight media proxy for Misskey servers. It is approximately 3KB in size and provides minimal functionality for proxying media.

## Features

- Lightweight and fast
- Easy to set up
- Responses are cached for a fixed period of time
- Docker support

## Install
### Install from Source 

1. Clone the repository.
```sh
git clone https://github.com/AmaseCocoa/media-proxy.git
cd media-proxy
```

2. Install the required dependencies.
```sh
pip install -r requirements.txt
```

### Install With Docker 

1. Pull the Docker image.
```sh
docker pull amasecocoa/media-proxy
```

2. Start the container.
```sh
docker run -d --name media-proxy -p 3003:3003 -e PORT=3030amasecocoa/media-proxy
```

## How To Use

### Start Server

Start the server with the following command.

```sh
python server.py
````

### Configuration

Use environment variables to configure settings.

- `PORT`: The port number the server listens on (default: 3003)
- `EXPIRES`: The length of time to cache media (default: 86400 (seconds))
- `CHUNK_SIZE`: The chunk size of the file to be read at a time. (default: 1048576 (bytes))

Example:

```sh
export PORT=8000
export EXPIRES=86400
export CHUNK_SIZE=5242880
```

### Example

To send an image request to a media proxy, use the following URL format:
```
http://host/proxy/image.webp?url=https://example.com/image.png
```

The `url` parameter is the URL of the image you wish to proxy.

## Develop

To set up the development environment, do the following: 

1. Install the dependencies.
```sh
pdm install
``` 

2. Start the server.
```sh
pdm run python server.py
```

## License

This project is released under the MIT License. See the [LICENSE](LICENSE) file for more information.