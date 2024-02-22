#FROM buildbase as build

#----------- below here would be buildbase --------------------

FROM python:3.9-bookworm as build

RUN sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list.d/debian.sources && \
  apt-get update && \
  apt-get install -y \
    curl \
    gnupg \
    gnupg1 \
    gnupg2 \
    python3 \
    python3-dev \
    virtualenv \
    build-essential \
    git \
    wget \
    rsync \
    python3-pip \
    binutils \
    libproj-dev \
    gdal-bin \
    zip \
    postgresql-client \
  && apt-get clean

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_ROOT_USER_ACTION=ignore

WORKDIR /app/code

RUN python -m venv /app/venv && \
    pip install pip-tools

# Enable the venv
ENV PATH="/app/venv/bin:$PATH"

#----------- above here would be buildbase --------------------

COPY . /app/code

RUN pip install -r requirements.txt
RUN python manage.py collectstatic --noinput --clear

#---------------------------------------------------------------------
# Now, the email templates

FROM node:20-alpine as email_templates

COPY . /app/code

RUN cd /app/code/mjml && \
    yarn && \
    ./convert

# Remove files not related to the templates we just converted
RUN rm -rf /app/code/mjml/node_modules && \
    find /app/code -type f -not -name \*.html.jinja2 -delete && \
    find /app/code -empty -type d -delete

#---------------------------------------------------------------------
# And finally, the runnable image

FROM python:3.9-slim-bookworm as runner

LABEL org.opencontainers.image.source=https://github.com/karrot-dev/karrot-backend

ENV PYTHONUNBUFFERED=1

# Only dependencies needed for runtime
RUN sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list.d/debian.sources && \
  apt-get update && \
  apt-get install -y \
    git \
    gdal-bin \
    libmaxminddb0 \
    libmaxminddb-dev \
    geoipupdate \
    libmagic1 \
  && apt-get clean

ARG USERNAME=karrot
ARG UID=1000
ARG GID=1000

RUN groupadd --gid $GID $USERNAME && \
   useradd --uid $UID -g $GID -m $USERNAME

# Copies code + dependencies
COPY --from=build /app /app

# Copies email templates
COPY --from=email_templates /app /app

RUN chown -R $UID:$GID /app

# Enable the venv
ENV PATH="/app/venv/bin:$PATH"

USER $USERNAME
WORKDIR /app/code

