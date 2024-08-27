FROM python:3.12.5-slim-bookworm
WORKDIR /mediaproxy

COPY . .

RUN apt-get update && apt-get install -y libmimalloc2.0 libmimalloc-dev
RUN pip install -U pip && \
    pip install --no-cache-dir -r /mediaproxy/requirements.txt

ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libmimalloc.so
CMD ["python3", "./server.py"]