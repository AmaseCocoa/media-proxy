FROM python:3.12.5-slim-bookworm
WORKDIR /mediaproxy

COPY . .

RUN apt-get update -qq && apt -y upgrade && \
    apt-get install -y libvips-dev libmimalloc2.0 libmimalloc-dev && \
    pip install -U pip && \
    pip install --no-cache-dir -r /mediaproxy/requirements.txt && \
    pip install uvloop && \
    rm -rf /var/lib/apt/lists/*

ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libmimalloc.so
CMD ["python3", "./server.py"]