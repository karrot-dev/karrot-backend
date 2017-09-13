to build pip dependencies:

```
sudo apt-get install postgresql-server-dev-9.6 python3-dev dev
```

Create db user with permissions:

```
createuser fstool
sudo -u postgres psql
> alter user "fstool" with password 'fstool';
> grant all privileges on database "fstool" to "fstool";
```

Give deploy user postgres permissions
in `/etc/postgresql/9.6/main/pg_hba.conf`:

```
local	all		deploy					peer
```

Add deploy user:

```
createuser deploy
sudo -u postgres psql
> alter user deploy createdb;
```

Setup uwsgi:

```
sudo apt-get install uwsgi uwsgi-plugin-python3
```

create /etc/uwsgi/apps-available/fstool.ini

```
[uwsgi]
project = karrot-backend
base = /home/deploy

chdir = %(base)/%(project)
home = %(base)/%(project)/env
module = config.wsgi:application

master = true
processes = 2

socket = /tmp/fstool.sock

touch-reload = /tmp/fstool.reload

chmod-socket = 664
vacuum = true

```

```
cd /etc/uwsgi/apps-enabled/
sudo ln -s ../apps-available/fstool.ini
```

Create nginx config:

```
/etc/nginx/sites-available/fstool
```

```
upstream websocket {
    server localhost:5090;
}

upstream django {
    server unix:/tmp/fstool.sock;
}

map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {

    server_name foodsaving.world;

    listen 443 ssl http2;
    listen [::]:443 ssl http2;

    ssl_certificate /var/www/fstool/cert/fullchain.pem;
    ssl_certificate_key /var/www/fstool/cert/key.pem;

    root /home/deploy/public-angular;

    location / {
        try_files $uri /index.html;
    }

    location /api/ {
        include uwsgi_params;
        uwsgi_pass django;

        uwsgi_param Host $host;
        uwsgi_param X-Real-IP $remote_addr;
        uwsgi_param X-Forwarded-For $proxy_add_x_forwarded_for;
        uwsgi_param X-Forwarded-Proto $http_x_forwarded_proto;
    }

    location /socket/ {
        proxy_pass http://websocket;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    } 

}

```

symlink it to sites-enabled:

```
cd /etc/nginx/sites-enabled
ln -s ../sites-available/fstool .
```

Clone the backend repo to `/home/deploy/karrot-backend` and create the virtualenv:

```
git clone https://github.com/yunity/karrot-backend.git
virtualenv --python=python3 --no-site-packages karrot-backend/env
```

Install `pip-tools`, to allow the deploy script to run `pip-sync`

```
cd karrot-backend
source env/bin/activate
pip install pip-tools

# Now you can run pip-sync
```

Fix a package problem in Debian (pkg-resources is separated from setuptools)

```
source env/bin/activate
pip uninstall setuptools && pip install -U setuptools

# Now you can try python manage.py runserver for testing
```

For running the backend in production, do

```
systemctl start uwsgi
```