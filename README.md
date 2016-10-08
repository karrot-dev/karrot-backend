[![CircleCI](https://circleci.com/gh/yunity/yunity-core/tree/master.svg?style=svg)](https://circleci.com/gh/yunity/yunity-core/tree/master)

# foodsaving-backend

## Getting started
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

#### Ubuntu/Debian
As the foodsaving tool requires relatively recent versions of some packages, using Ubuntu 15.10 or greater is required.

```sh
sudo apt-get install git redis-server python3 python3-dev python-virtualenv postgresql postgresql-server-dev-9.4 gcc build-essential g++ libffi-dev libncurses5-dev
```

#### OpenSUSE Leap

All packages should be available in the default repositories `repo-oss` and `repo-non-oss`.

```sh
sudo zypper install python-virtualenv postgresql-devel postgresql python-redis redis
```

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

# Contributing to foodsaving-backend
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
A live instance of the foodsaving tool is running at https://fstool.yunity.org. The database will be emptied regularly, any data may be available to the public. Use at your own risk for testing.
Use https://fstool.yunity.org/api/ for a browseable API and for API requests.

A session is identified via the sessionid cookie. Additionally, a csrftoken cookie is set with each POST request (initially for the login). To issue any other POST request than a login, you need to provide the contents of the csrftoken cookie in the X-CSRFToken header field. The session cookie is automatically appended to each request by the browser.
For more detailled notes on how to implement this in javascript, see https://docs.djangoproject.com/en/1.9/ref/csrf/

# Hints

## Speed up testing: relaxed postgres fsync behaviour
On a local setup, you may want to change fsync behaviour to speed up the test running process. You may want to make sure to understand the implications but on a dev machine this should be fine.

Edit /var/lib/postgres/data/postgresql.conf and add or edit

```
fsync = off
```

## Update requirement packages
pip-tools is used to manage requirements. To use the latest possible requirements, do:

- `pip install pip-tools`
- `pip-compile --upgrade`

## IDE
We use PyCharm for development. The open source free professional licences are still pending, for now use the community edition from https://www.jetbrains.com/pycharm/download/.

Archlinux users may install pycharm-community from the aur.

Please set the python interpreter to the virtual env python created during during the setup.

### Vim

For all those who love Vim, just enable syntax checking and add python and django plugins to Vim. Follow [using vim with django](https://code.djangoproject.com/wiki/UsingVimWithDjango).
