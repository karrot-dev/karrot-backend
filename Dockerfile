# syntax=docker/dockerfile:1.7-labs
# ^ this enables the "COPY --parents" syntax
# remove this once it's supported widely enough
# https://docs.docker.com/reference/dockerfile/#copy---parents

ARG PYTHON_VERSION=3.11
ARG NODE_VERSION=20

FROM docker.io/python:${PYTHON_VERSION}-bookworm as build

RUN <<EOF
sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list.d/debian.sources
apt-get update
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
  postgresql-client
apt-get clean
EOF

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_ROOT_USER_ACTION=ignore

WORKDIR /app/code

RUN <<EOF
python -m venv /app/venv
pip install pip-tools
EOF

# Enable the venv
ENV PATH="/app/venv/bin:$PATH"

COPY requirements.txt /app/code

RUN pip install -r requirements.txt

#---------------------------------------------------------------------
# Now, the email templates

FROM docker.io/node:${NODE_VERSION}-alpine as email_templates

COPY --parents karrot/*/templates/*.mjml /app/code
COPY mjml /app/code/mjml

RUN <<EOF
cd /app/code/mjml
yarn
./convert
EOF

# Remove files not related to the templates we just converted
RUN <<EOF
rm -rf /app/code/mjml/node_modules
find /app/code -type f -not -name \*.html.jinja2 -delete
find /app/code -empty -type d -delete
EOF

#---------------------------------------------------------------------
# And finally, the runnable image

FROM docker.io/python:${PYTHON_VERSION}-slim-bookworm as runner

ENV PYTHONUNBUFFERED=1

# Only dependencies needed for runtime
RUN <<EOF
sed -i -e's/ main/ main contrib non-free/g' /etc/apt/sources.list.d/debian.sources
apt-get update
apt-get install -y \
  git \
  gpg \
  curl \
  gdal-bin \
  libmaxminddb0 \
  libmaxminddb-dev \
  geoipupdate \
  libmagic1
apt-get clean
EOF

# Run as unprivileged user
ARG USERNAME=karrot
ARG UID=1000
ARG GID=1000

RUN <<EOF
groupadd --gid $GID $USERNAME
useradd --uid $UID -g $GID -m $USERNAME
EOF

WORKDIR /app/code

# Enable the venv
ENV PATH="/app/venv/bin:$PATH"

# Copies dependencies
COPY --from=build /app/venv /app/venv

# Copies code
COPY . /app/code

# Copies email templates
COPY --from=email_templates /app/code /app/code

RUN python manage.py collectstatic --noinput --clear

RUN chown -R $UID:$GID /app

USER $USERNAME
