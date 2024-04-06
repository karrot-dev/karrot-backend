# karrot-backend

Django API server for the _karrot_ frontend

Our issues are tracked on our [community board](https://community.karrot.world/c/32/l/latest?board=default), and also on [karrot-frontend](https://codeberg.org/karrot/karrot-frontend/issues) issues.

[![status-badge](https://ci.codeberg.org/api/badges/13131/status.svg)](https://ci.codeberg.org/repos/13131)

## Developer setup

### Recommended setup

This runs all the app code locally on your machine, and the services (postgresql, redis, etc.) in containers.

#### Prerequisites

- python
  - Karrot is written in python
  - optionally you can use [mise](https://mise.jdx.dev) to install a specific version, run `mise install`
  - otherwise get a version 3 of python
  - if possible use the same version as listed at the top of the `Dockerfile`
- nodejs
  - this is used for email templates as we use [mjml.io](https://mjml.io)
  - install it via your package manager or from [nodejs.org](https://nodejs.org)
  - if you are using mise, `mise install` will have already installed it previously
- yarn (classic)
  - used to install nodejs dependencies
  - install it via your package manager or with `npm install --global yarn`
- a container runtime
  - used to run the services (postgresql, redis, etc.)
  - podman is the recommended option
    - install podman via package manager or from [podman.io](https://podman.io)
  - docker is just fine too
    - install docker via package manager or from [docs.docker.com/get-docker](https://docs.docker.com/get-docker)
  - nerdctl is for advanced users who know what they're doing
    - install nerdctl via package manager or see [github.com/containerd/nerdctl](https://github.com/containerd/nerdctl)
  - if you don't like the autodetected choice, you can set `RUNTIME=<runtime>"` in `.env`
    - e.g. `RUNTIME=nerdctl`

#### Setup

```commandline
# create a virtualenv
python -m venv .venv

# if not using mise, you'll need to activate the virtualenv
source .venv/bin/activate

# install deps
./sync.py

# start it all up
./scripts/dev
```

It might take some time on first run, as it has to download some container images.

Once it's ready you should a line something like:

```bash
12:37:11 web.1     | Listening on TCP address 127.0.0.1:8000
```

#### Up and running

Everything should be up and running now! Visiting http://localhost:8000 should show you "not found".

More interesting places to visit are:
- http://localhost:8000/docs/ - API documentation
- http://localhost:8000/api/bootstrap/ - a request that will show you some json
- http://localhost:8000/_templates - email template previews
- http://localhost:8081/ - pgweb database UI
- http://localhost:1080/ - maildev mail catcher UI

If you want a Karrot frontend, you have two options:
1. setup [karrot-frontend](https://codeberg.org/karrot/karrot-frontend) and set `BACKEND=http://127.0.0.1:8000` in `.env`
2. download and unpack the .tar.gz archive from a [recent release](https://codeberg.org/karrot/karrot/releases) and configure `FRONTEND_DIR` to point to the folder

You can create some interesting usable data by running:

```bash
./manage.py create_sample_data
```

After that you can login as `foo@foo.com` / `foofoo`

Be sure to checkout the [Karrot Developer Documentation](https://docs.karrot.world/dev/getting-started) too.

### Advanced: Manual setup

You can also just run everything locally if you want:

- run postgresql
- run redis
- create `config/local_settings.py` and configure it to point to those
  - you can reference `config/local_settings.py.example` to see what to set

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

## Django quick introduction

The manage.py application can be used to perform administrative tasks:

  - makemigrations: Create database migrations
  - migrate: Apply database migrations
  - shell\_plus: for playing in a django python environment
  - test: Run automated tests

You can launch them like this:

```
./manage.py makemigrations
./manage.py migrate
./manage.py shell_plus
./manage.py test
```

## Speed up testing

When running tests, use `./scripts/test`, which will configure the test runner to use [config/test_settings.py](config/test_settings.py). It is much faster.

*Parallel testing:* Running the tests in parallel process can increase testing speed significantly:

```
./scripts/test --parallel auto
```

*Run tests selectively:* If you want to run only a single test, let's say
`TestGroupManager` in `karrot/groups/tests/test_model.py`, you can do so by
using dot-syntax:

```
./scripts/test karrot.groups.tests.test_model.TestGroupManager
```

## Email template viewer

When editing emails it's useful to be able to see how they will be rendered.

Assuming the server is running you can visit [localhost:8000/\_templates](http://localhost:8000/_templates).

When running `./scripts/dev` the templates will automatically be compiled for you.

If you need to run the conversion manually though, you can run:
```
cd mjml
yarn
./convert
```

_Note: you should never edit `.html.jinja2` files directly._

Enjoy! ... oh and be sure to visit https://mjml.io/documentation/#components to find some nice components to use.
