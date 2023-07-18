# karrot-backend

Django API server for the _karrot_ frontend

Our issues are tracked in [karrot-frontend](https://github.com/karrot-dev/karrot-frontend/issues). We plan to unite karrot-backend, karrot-frontend and related repos in near future.

[![CircleCI](https://circleci.com/gh/karrot-dev/karrot-backend/tree/master.svg?style=svg)](https://circleci.com/gh/karrot-dev/karrot-backend/tree/master)
[![codecov](https://codecov.io/gh/karrot-dev/karrot-backend/branch/master/graph/badge.svg?token=U2gJZBxdkU)](https://codecov.io/gh/karrot-dev/karrot-backend)

## Developer setup

### Experimental new podman setup

This runs all the app code locally on your machine, and the services (database, redis, etc.) in containers using podman.

Prerequisites:
- python3 (I use [rtx](https://github.com/jdxcode/rtx) to install specific version)
- [podman](https://podman.io/) (docker without the daemon or root power)

```commandline
# if not using rtx, create a virtualenv
python -m venv env

# install deps
./sync.py

# start it all up
./scripts/dev
```

Everything should be up and running now.

### docker-compose setup

Includes backend, frontend, mail catcher, postgres, redis, etc..

Head over to [karrot-dev/karrot-docker](https://github.com/karrot-dev/karrot-docker) for further instructions.

### Manual setup

You can also just run everything locally if you want.

If you want help/tips you can chat with us at:
- [#karrot:matrix.org](https://matrix.to/#/#karrot:matrix.org)
- [Karrot Team & Feedback](https://karrot.world/#/groupPreview/191) group on Karrot itself

## Configuration options

If you want to configure some options, create a `.env` file. Check [config/options.env](config/options.env) (base config) and/or [config/dev.env](config/dev.env) (if `MODE=dev`) for ideas of what to put in it.

These are processed by [config/options.py](config/options.py) and then [config/settings.py](config/settings.py).

You can also create a `config/local_settings.py` if you want, and it'll override everything, but better to use a `.env` if you can.

## Coding guidelines

We use various code tools, which are run when you commit using [pre-commit](https://pre-commit.com/). Check [.pre-commit-config.yaml](.pre-commit-config.yaml) to see more there.

In short, if you commit, and it makes changes, add the changes, and commit again.

## Using the API

A live dev instance of _karrot_ is running at https://dev.karrot.world/. See https://dev.karrot.world/docs/ for API documentation. Most endpoints are only available to authenticated users. Be sure to create an account and log in to see all endpoints.

## IDE

Most of karrot developers use [PyCharm](https://www.jetbrains.com/pycharm/download/). We have some licenses available for the professional version. The free community edition also works well.

To get proper introspection and support from PyCharm, it's necessary to set up a virtualenv. Run this inside the backend directory:

```
python -m venv env
source env/bin/activate
./sync.py
```

## Django quick introduction

The manage.py application can be used to perform administrative tasks:

  - makemigrations: Create database migrations
  - migrate: Apply database migrations
  - shell\_plus: for playing in a django python environment
  - test: Run automated tests

You can launch them via docker-compose, for example:

```
docker-compose exec backend ./manage.py makemigrations
docker-compose exec backend ./manage.py migrate
```

If you spend too much time typing those long commands, consider creating your own [bash aliases](https://askubuntu.com/questions/17536/how-do-i-create-a-permanent-bash-alias).


## Speed up testing

When running tests, use `./scripts/test`, which will configure the test runner to use [config/test_settings.py](config/test_settings.py). It is much faster.

*Parallel testing:* Running the tests in parallel process can increase testing
speed significantly. To execute the whole test suite on a CPU with 4 kernels,
you may want to use:

```
./scripts/test --parallel 4
```

*Run tests selectively:* If you want to run only a single test, let's say
`TestGroupManager` in `karrot/groups/tests/test_model.py`, you can do so by
using dot-syntax:

```
./scripts/test karrot.groups.tests.test_model.TestGroupManager
```

## Email template viewer

When editing emails it's useful to be able to see how they will be rendered.

Assuming the server is running you can visit visit [localhost:8000/\_templates](http://localhost:8000/_templates).

To compile the `.mjml` templates to `.html.jinja2` files you can run:
```
cd mjml
yarn
./convert
```

_Note: you should never edit `.html.jinja2` files directly._

Enjoy! ... oh and be sure to visit https://mjml.io/documentation/#components to find some nice components to use.
