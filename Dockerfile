FROM python:3.12.5-slim-bookworm
WORKDIR /mediaproxy

COPY . .

RUN apt-get update -qq && apt -y upgrade && \
    apt-get install -y git build-essential libpng-dev wget pkg-config glib2.0-dev libexpat1-dev autoconf nasm libtool dpkg g++ && \
    apt-get install -y libmimalloc2.0 libmimalloc-dev
RUN wget https://github.com/jcupitt/libvips/releases/download/v8.11.0/vips-8.11.0.tar.gz
RUN tar xf vips-8.11.0.tar.gz && cd vips-8.11.0 && ./configure && make && make install && ldconfig

RUN pip install -U pip && \
    pip install --no-cache-dir -r /mediaproxy/requirements.txt && \
    pip install uvloop

ENV LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libmimalloc.so
CMD ["python3", "./server.py"]