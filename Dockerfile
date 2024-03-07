# syntax=docker/dockerfile-upstream:master-labs

ARG PYTHON_VERSION=3.11
ARG NODE_VERSION=20

FROM docker.io/python:${PYTHON_VERSION}-bookworm as build

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

COPY requirements.txt /app/code

RUN pip install -r requirements.txt

#---------------------------------------------------------------------
# Now, the email templates

FROM docker.io/node:${NODE_VERSION}-alpine as email_templates

COPY --parents karrot/*/templates/*.mjml /app/code/karrot
COPY mjml /app/code/mjml

RUN find /app/code

RUN cd /app/code/mjml && \
    yarn && \
    ./convert

# Remove files not related to the templates we just converted
RUN rm -rf /app/code/mjml/node_modules && \
    find /app/code -type f -not -name \*.html.jinja2 -delete && \
    find /app/code -empty -type d -delete

#---------------------------------------------------------------------
# And finally, the runnable image

FROM docker.io/python:${PYTHON_VERSION}-slim-bookworm as runner

ENV PYTHONUNBUFFERED=1

# Only dependencies needed for runtime
RUN sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list.d/debian.sources && \
  apt-get update && \
  apt-get install -y \
    git \
    curl \
    gdal-bin \
    libmaxminddb0 \
    libmaxminddb-dev \
    geoipupdate \
    libmagic1 \
  && apt-get clean

# Run as unprivileged user
ARG USERNAME=karrot
ARG UID=1000
ARG GID=1000

RUN groupadd --gid $GID $USERNAME && \
    useradd --uid $UID -g $GID -m $USERNAME

WORKDIR /app/code

# Enable the venv
ENV PATH="/app/venv/bin:$PATH"

# Copies dependencies
COPY --from=build /app/venv /app/venv

COPY . /app/code

# Copies email templates
COPY --from=email_templates /app/code /app/code

RUN python manage.py collectstatic --noinput --clear

RUN chown -R $UID:$GID /app

USER $USERNAME
