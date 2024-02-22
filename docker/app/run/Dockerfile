FROM python:3.9-bookworm

LABEL org.opencontainers.image.source=https://github.com/karrot-dev/karrot-backend

RUN sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list.d/debian.sources && \
  apt-get update && \
  apt-get install -y \
    gdal-bin \
    libmaxminddb0 \
    libmaxminddb-dev \
    geoipupdate
