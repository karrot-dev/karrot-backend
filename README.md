# karrot-backend

Django API server for the _karrot_ frontend

Our issues are tracked in [karrot-frontend](https://github.com/yunity/karrot-frontend/issues). We plan to unite the karrot-backend, karrot-frontend and related repos in near future.

[![CircleCI](https://circleci.com/gh/yunity/karrot-backend.svg?style=svg)](https://circleci.com/gh/yunity/karrot-backend)
[![codecov](https://codecov.io/gh/yunity/karrot-backend/branch/master/graph/badge.svg)](https://codecov.io/gh/yunity/karrot-backend)

## Developer setup

The recommended way to getting your developer environment setup is docker-compose - includes backend, frontend, mail catcher, postgres, redis, etc..

Head over to [yunity/karrot-docker](https://github.com/yunity/karrot-docker) for further instructions.

If you can't or don't want to use docker-compose, look into [SETUP.md](SETUP.md) for other ways.

## Django quick introduction

The manage.py application can be used to perform administrative tasks:

  - makemigrations: Create database migrations
  - migrate: Apply database migrations
  - shell\_plus: (requires ipython) for playing in a django python environment
  - test: Run automated tests

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
A live instance of _karrot_ is running at https://karrot.world/. Use https://karrot.world/api/ for a browseable API and for API requests.

A session is identified via the sessionid cookie. Additionally, a csrftoken cookie is set with each POST request (initially for the login). To issue any other POST request than a login, you need to provide the contents of the csrftoken cookie in the X-CSRFToken header field. The session cookie is automatically appended to each request by the browser.
For more detailled notes on how to implement this in javascript, see https://docs.djangoproject.com/en/1.9/ref/csrf/

# Hints

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
Most of karrot developers use [PyCharm](https://www.jetbrains.com/pycharm/download/). We have some licenses available for the professional version. The free community edition also works well.

To get proper introspection and support from PyCharm, it's necessary to set up a virtualenv. Run this inside the backend directory:

```
virtualenv env
source ./env/bin/activate
pip install pip-tools
./sync.py
```

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
