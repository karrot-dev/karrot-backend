# karrot-backend

Django API server for the _karrot_ frontend 

[![CircleCI](https://circleci.com/gh/yunity/karrot-backend.svg?style=svg)](https://circleci.com/gh/yunity/karrot-backend)
[![codecov](https://codecov.io/gh/yunity/karrot-backend/branch/master/graph/badge.svg)](https://codecov.io/gh/yunity/karrot-backend)

There are 3 approaches to getting your developer environment setup:

1. [single docker container](#getting-started-with-docker) - includes backend, postgres, and redis in one container
2. [local install](#local-install) - install everything on your system ([Arch](#arch-linux), [Ubuntu](#ubuntu-or-debian), [Debian](#ubuntu-or-debian), [macOS](#mac-os), [OpenSUSE Leap](#opensuse-leap))
3. [docker-compose setup](#docker-compose) - includes backend, frontend, mail catcher, postgres, redis, etc..

## Getting started with Docker

You can automate your setup with [Docker](https://www.docker.com/what-docker).

Build the docker container:
```sh
docker build -t backend .
```
Run this container, including your most recent source code changes:

```sh
docker run -d -p 8000:8000 -v $PWD/foodsaving:/karrot-backend/foodsaving backend
```

Note 1: This assumes that your terminal's working directory is in the karrot-backend directory, i.e. the directory you cloned from Github.
Note 2: Only changes you make in the "foodsaving" directory are included.

The test data are automatically created in the container. You can see log-in details after running this command:

```sh
docker logs -f CONTAINER
```

With this data, you can log in as one of the printed e-mail addresses with password 123

The server is already running in Docker container.

## Local install
### Install requirements

- python3.5 or greater/virtualenv
- postgresql >=9.4
- redis-server

#### Arch Linux

All packages can be obtained from core, extra or community repositories. When queried, chose to install all packets out of base-devel.

```sh
sudo pacman -S base-devel python python-pip python-virtualenv postgresql python-redis redis
```

Afterwards, do the first-time postgres setup (taken from the [Arch Linux wiki](https://wiki.archlinux.org/index.php/PostgreSQL))

```sh
sudo -i -u postgres
initdb --locale en_US.UTF-8 -E UTF8 -D '/var/lib/postgres/data'
```

By default, Arch Linux does not start the installed services. Do it manually by executing

```sh
sudo systemctl start postgresql.service
sudo systemctl start redis.service
```

You can add them to autostart as well:

```sh
sudo systemctl enable postgresql.service
sudo systemctl enable redis.service
```

#### Ubuntu or Debian
As _karrot_ requires relatively recent versions of some packages, using Ubuntu 15.10 or greater is required.

```sh
sudo apt-get install git redis-server python3 python3-dev python-virtualenv postgresql postgresql-server-dev-9.4 gcc build-essential g++ libffi-dev libncurses5-dev
```
#### Mac OS
For Mac OS, you will need homebrew. With homebrew you can install all packages.

```sh
brew install postgresql
initdb /usr/local/var/postgres -E utf8
brew services start postgresql
brew install redis
brew services start redis
```

#### OpenSUSE Leap
All packages should be available in the default repositories `repo-oss` and `repo-non-oss`.

```sh
sudo zypper install python-virtualenv postgresql-devel postgresql python-redis redis
```

### Setup virtualenv

The backend is meant to be run inside a python virtualenv that is independent from your systems python packages.

As we installed `python3` and `virtualenv` earlier, we can now proceed to create the environment and download the necessary packages:

```
# inside the karrot-backend folder
virtualenv --no-site-packages --pyton=python3 env
. ./env/bin/activate
pip install pip-tools
./sync.py
```

This step might be useful in the docker compose setup as well, to have packages available locally for development.

## Docker Compose

Head over to [yunity/foodsaving-docker](https://github.com/yunity/foodsaving-docker) for further instructions.

## Django quick introduction
Before using any tools from the shell, you need to activate the virtualenv:

```sh
source ./env/bin/activate
```

The manage.py application can be used to perform administrative tasks:

  - makemigrations: Create database migrations
  - migrate: Apply database migrations
  - shell\_plus: (requires ipython) for playing in a django python environment
  - test: Run automated tests

## API Documentation

A swagger description file is generated at /doc. You can pass it to any swagger installation.

## Django application settings

In development, you can add and override local settings in
`config/local_settings.py`, which is present in `.gitignore` and hence out of
version control. If the file is not present, i.e. in production, nothing
happens.

Change the following values in the dictionary `DATABASES` in the file `local_settings.py (example)`: `NAME`, `USER` and `PASSWORD`. Change also variables `INFLUXDB_DATABASE` and `DEFAULT_FROM_EMAIL` in `local_settings.py (example)` accordingly.

Set your database `PostgreSQL` with the correct name and user.

#### Mac OS

First, initialize the database.

```sh
initdb /usr/local/var/postgres
```

Now, create the user you used in `local_settings.py`.

```sh
createuser --pwprompt *user_name*
```

And create the database with the name you used in `local_settings.py`.

```sh
createdb -O *user_name* -Eutf8 *db_name*
```

You can run the server with `python manage.py runserver`.


## Migrations

Sometimes you will need to create Django migrations. 

```
source env/bin/activate
./manage.py makemigrations
./manage.py migrate
```

In particular, before you launch your backend for the very first time you will need to execute `./manage.py migrate` to initialize your database.

# Contributing to karrot-backend

To contribute, please get in contact with us. We want to follow a pull request / code review cycle as soon as possible but in our early design stages we prefer to work in teams at the same desk.
We use

- github issues for development tasks
- [Slack](https://yunity.slack.com) as team communication, not only for development

## Coding guidelines

We follow PEP8 with the same rules as the [Django project](https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/).
As always, the coding style may not apply at some parts.
You can execute `flake8` in the repository root to check your code.

Code will only be accepted into `master` if it passes the PEP8 test.

## Using the API
A live instance of _karrot_ is running at https://foodsaving.world/. Use https://foodsaving.world/api/ for a browseable API and for API requests.

A session is identified via the sessionid cookie. Additionally, a csrftoken cookie is set with each POST request (initially for the login). To issue any other POST request than a login, you need to provide the contents of the csrftoken cookie in the X-CSRFToken header field. The session cookie is automatically appended to each request by the browser.
For more detailled notes on how to implement this in javascript, see https://docs.djangoproject.com/en/1.9/ref/csrf/

# Hints

## Speed up testing

### Relaxed postgres fsync behaviour
On a local setup, you may want to change fsync behaviour to speed up the test running process. You may want to make sure to understand the implications but on a dev machine this should be fine.

Edit /var/lib/postgres/data/postgresql.conf and add or edit

```
fsync = off
```

### Parallel testing
Running the tests in parallel process can increase testing speed significantly. 
To execute the whole test suite on a CPU with 4 kernels, you may want to use:

```
python manage.py test --parallel=4
```

For further information, see https://docs.djangoproject.com/en/2.0/ref/django-admin/#cmdoption-test-parallel.

## Update requirement packages
pip-tools is used to manage requirements. To use the latest possible requirements, do:

- `pip install pip-tools`
- `pip-compile --upgrade`

## IDE
We use [PyCharm](https://www.jetbrains.com/pycharm/download/) for development. We have some licenses available for the professional version which includes Django support specifically. The free community edition also works well.

You can use whatever you want of course.

Please set the python interpreter to the virtual env python created during during the setup.

### Vim

For all those who love Vim, just enable syntax checking and add python and django plugins to Vim. Follow [using vim with django](https://code.djangoproject.com/wiki/UsingVimWithDjango).

# Email template viewer

When editing emails it's useful to be able to see how they will be rendered.

Assuming the server is running you can visit visit [localhost:8000/\_templates](http://localhost:8000/_templates).

To compile the `.mjml` templates to `.html.jinja2` files you can run:
```
cd mjml
yarn
./convert
```

If you want to watch for changes, and support hot reloading then run:

```
./convert --watch
```

(refresh your browser after starting the server as the websocket is not reconnecting)

_Note: you should never edit `.html.jinja2` files directly._ 


Enjoy! ... oh and be sure to visit https://mjml.io/documentation/#components to find some nice components to use.
