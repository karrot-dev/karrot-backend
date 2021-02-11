# yapf: disable
"""
Django settings for Karrot.

For more information on this file, see
https://docs.djangoproject.com/en/dev/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/dev/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
import redis

from dotenv import load_dotenv

from karrot.groups import themes
from config.options import get_options

load_dotenv()

options = get_options()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Karrot constants

MODE = options['MODE']

if MODE not in ('dev', 'prod',):
    raise Exception('MODE must be one of dev|prod, not {}'.format(MODE))

is_dev = MODE == 'dev'

DEBUG = is_dev

# Generic
DESCRIPTION_MAX_LENGTH = 100000
NAME_MAX_LENGTH = 80
# Names that shouldn't be used used by groups or users because they are either confusing or unspecific
# Values are case-insensitive
RESERVED_NAMES = (
    'karrot',
    'foodsaving',
    'foodsharing',
)

# Users
# Verification codes:
# Time until a verification code expires
EMAIL_VERIFICATION_TIME_LIMIT_HOURS = 7 * 24
PASSWORD_RESET_TIME_LIMIT_MINUTES = 180
ACCOUNT_DELETE_TIME_LIMIT_MINUTES = 180

# Groups
GROUP_EDITOR_TRUST_MAX_THRESHOLD = 3
# For marking groups inactive
NUMBER_OF_DAYS_UNTIL_GROUP_INACTIVE = 14
# For marking users inactive
NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP = 30
# For removing inactive users from groups
NUMBER_OF_INACTIVE_MONTHS_UNTIL_REMOVAL_FROM_GROUP_NOTIFICATION = 6
NUMBER_OF_DAYS_AFTER_REMOVAL_NOTIFICATION_WE_ACTUALLY_REMOVE_THEM = 7
# set group theme
GROUP_THEME_DEFAULT = themes.GroupTheme.FOODSAVING

# Places
STORE_MAX_WEEKS_IN_ADVANCE = 52

# Activities
FEEDBACK_POSSIBLE_DAYS = 30
ACTIVITY_DUE_SOON_HOURS = 6
ACTIVITY_REMINDER_HOURS = 3
ACTIVITY_LEAVE_LATE_HOURS = 24

# Conversations
MESSAGE_EDIT_DAYS = 2
CONVERSATION_CLOSED_DAYS = 7

# Issues
VOTING_DURATION_DAYS = 7
VOTING_DUE_SOON_HOURS = 12

KARROT_LOGO = options['SITE_LOGO']

ASGI_APPLICATION = 'config.asgi_app.application'

# Django configuration
INSTALLED_APPS = (
    # Should be loaded first
    'channels',
    'raven.contrib.django.raven_compat',

    # core Django
    'django.contrib.admin',
    'django.contrib.admindocs',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'django.contrib.messages',
    'django.contrib.postgres',

    # Application
    'karrot',
    'karrot.applications.ApplicationsConfig',
    'karrot.base.BaseConfig',
    'karrot.bootstrap.BootstrapConfig',
    'karrot.community_feed.CommunityFeedConfig',
    'karrot.issues.IssuesConfig',
    'karrot.userauth.UserAuthConfig',
    'karrot.subscriptions.SubscriptionsConfig',
    'karrot.users.UsersConfig',
    'karrot.conversations.ConversationsConfig',
    'karrot.history.HistoryConfig',
    'karrot.groups.GroupsConfig',
    'karrot.places.PlacesConfig',
    'karrot.unsubscribe',
    'karrot.offers.OffersConfig',
    'karrot.activities.ActivitiesConfig',
    'karrot.invitations.InvitationsConfig',
    'karrot.template_previews',
    'karrot.webhooks.WebhooksConfig',
    'karrot.notifications.NotificationsConfig',
    'karrot.stats',
    'karrot.status.StatusConfig',

    # Django packages
    'django_extensions',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_swagger',
    'anymail',
    'influxdb_metrics',
    'timezone_field',
    'django_jinja',
    'versatileimagefield',
    'huey.contrib.djhuey',
    'silk',
)

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': ('rest_framework.permissions.AllowAny', ),
    'DEFAULT_RENDERER_CLASSES': ('rest_framework.renderers.JSONRenderer', ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
    ),
    'EXCEPTION_HANDLER': 'karrot.utils.misc.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.coreapi.AutoSchema',
}

MIDDLEWARE = (
    'silk.middleware.SilkyMiddleware',
    'influxdb_metrics.middleware.InfluxDBRequestMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # 'whitenoise.middleware.WhiteNoiseMiddleware', # TODO: do I need this?
    'django.middleware.common.CommonMiddleware',
)

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        "BACKEND": "django_jinja.backend.Jinja2",
        "APP_DIRS": True,
        "OPTIONS": {
            "match_extension": ".jinja2",
            "extensions": [
                "jinja2.ext.i18n",
            ],
            "autoescape": True,
            "environment": "karrot.utils.email_utils.jinja2_environment"
        }
    },
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.contrib.auth.context_processors.auth',
                'django.template.context_processors.debug',
                'django.template.context_processors.i18n',
                'django.template.context_processors.media',
                'django.template.context_processors.static',
                'django.template.context_processors.tz',
                'django.template.context_processors.request',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': options['DATABASE_NAME'],
        'USER': options['DATABASE_USER'],
        'PASSWORD': options['DATABASE_PASSWORD'],
        'HOST': options['DATABASE_HOST'],
        'PORT': options['DATABASE_PORT'],
    }
}

REDIS_HOST = options['REDIS_HOST']
REDIS_PORT = options['REDIS_PORT']
REDIS_DB = options['REDIS_DB']
REDIS_URL = "redis://{}:{}/{}".format(REDIS_HOST, REDIS_PORT, REDIS_DB)

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

EMAIL_REPLY_DOMAIN = options['EMAIL_REPLY_DOMAIN']

EMAIL_BACKEND_NAME = options['EMAIL_BACKEND']

if EMAIL_BACKEND_NAME == 'postal':
    EMAIL_BACKEND = 'anymail.backends.postal.EmailBackend'
    ANYMAIL = {
        'POSTAL_API_URL': options['POSTAL_API_URL'],
        'POSTAL_API_KEY': options['POSTAL_API_KEY'],
        'POSTAL_WEBHOOK_KEY': options['POSTAL_WEBHOOK_KEY'],
    }
else:  # console is default anyway
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
    'django.contrib.auth.hashers.BCryptPasswordHasher',
]

VERSATILEIMAGEFIELD_SETTINGS = {
    'image_key_post_processor': 'versatileimagefield.processors.md5',
    # TODO: implement the proper way of auto creating images
    # See https://django-versatileimagefield.readthedocs.io/en/latest/improving_performance.html#auto-creating-sets-of-images-on-post-save
    # I previously had it locally set to False to not get exceptions for missing images
    # See https://github.com/respondcreate/django-versatileimagefield/issues/24#issuecomment-160674807
    'create_images_on_demand': True,
}

VERSATILEIMAGEFIELD_RENDITION_KEY_SETS = {
    'user_profile': [
        ('full_size', 'url'),
        ('thumbnail', 'thumbnail__120x120'),
        ('600', 'thumbnail__600x600'),
    ],
    'group_logo': [
        ('full_size', 'url'),
        ('thumbnail', 'thumbnail__120x120'),
        ('200', 'thumbnail__200x200'),
        ('600', 'thumbnail__600x600'),
    ],
    'offer_image': [
        ('full_size', 'url'),
        ('600', 'thumbnail__600x600'),
    ],
    'conversation_message_image': [
        ('full_size', 'url'),
        ('200', 'thumbnail__200x200'),
        ('600', 'thumbnail__600x600'),
    ]
}

# Silk profiler configuration
# User must login
SILKY_AUTHENTICATION = True
# User must have is_staff = True
SILKY_AUTHORISATION = True
# for now, log only requests that have recording enabled
SILKY_INTERCEPT_FUNC = lambda request: 'silky_record_requests' in request.COOKIES  # noqa: E731

# Internationalization
# https://docs.djangoproject.com/en/dev/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

STATIC_URL = '/static/'

CORS_ORIGIN_WHITELIST = []
# Allow all request origins. Will still require valid CSRF token and session information for modification but allows
# e.g. including the docs from any location
CORS_ORIGIN_ALLOW_ALL = True
CORS_ALLOW_CREDENTIALS = True

SESSION_COOKIE_HTTPONLY = True

AUTH_USER_MODEL = 'users.User'

LOGIN_URL = '/api-auth/login/'
LOGOUT_URL = '/api-auth/logout/'

SILENCED_SYSTEM_CHECKS = [
    'urls.W005',  # we don't need to reverse backend URLs
]

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}

FRONTEND_DIR = options['FRONTEND_DIR']

DEFAULT_FROM_EMAIL = options['EMAIL_FROM']
HOSTNAME = options['SITE_URL']
SITE_NAME = options['SITE_NAME']
MEDIA_ROOT = options['FILE_UPLOAD_DIR']

if options['FILE_UPLOAD_PERMISSIONS']:
    FILE_UPLOAD_PERMISSIONS = int(options['FILE_UPLOAD_PERMISSIONS'], 8)  # e.g. 0o640

if options['FILE_UPLOAD_DIRECTORY_PERMISSIONS']:
    FILE_UPLOAD_DIRECTORY_PERMISSIONS = int(options['FILE_UPLOAD_DIRECTORY_PERMISSIONS'], 8)  # e.g. 0o750

STATIC_ROOT = os.path.join(BASE_DIR, 'karrot', 'static')
MEDIA_URL = '/media/'

ALLOWED_HOSTS = [s.strip() for s in options['ALLOWED_HOSTS'].split(',')] if options['ALLOWED_HOSTS'] else []
CSRF_TRUSTED_ORIGINS = [s.strip() for s in options['CSRF_TRUSTED_ORIGINS'].split(',')] if options['CSRF_TRUSTED_ORIGINS'] else []

INFLUXDB_HOST = options['INFLUXDB_HOST']

INFLUXDB_DISABLED = not INFLUXDB_HOST

INFLUXDB_HOST = INFLUXDB_HOST
INFLUXDB_PORT = options['INFLUXDB_PORT']
INFLUXDB_USER = options['INFLUXDB_USER']
INFLUXDB_PASSWORD = options['INFLUXDB_PASSWORD']
INFLUXDB_DATABASE = options['INFLUXDB_NAME']
INFLUXDB_TAGS_HOST = options['INFLUXDB_HOST_TAG']
INFLUXDB_TIMEOUT = 5
INFLUXDB_USE_CELERY = False
INFLUXDB_USE_THREADING = True

SENTRY_DSN = options['SENTRY_DSN']
SENTRY_RELEASE = options['SENTRY_RELEASE']

# TODO: fix! should not use release if not set...
if SENTRY_DSN:
    RAVEN_CONFIG = { 'dsn': SENTRY_DSN }
    if SENTRY_RELEASE:
        RAVEN_CONFIG['release'] = SENTRY_RELEASE

SECRET_KEY = options['SECRET_KEY']
FCM_SERVER_KEY = options['FCM_SERVER_KEY']
ADMIN_CHAT_WEBHOOK = options['ADMIN_CHAT_WEBHOOK']

WORKER_IMMEDIATE = options['WORKER_IMMEDIATE'] == 'true'
WORKER_COUNT = int(options['WORKER_COUNT'])

if WORKER_IMMEDIATE:
    HUEY = {
        'immediate': True,
    }
else:
    pool = redis.ConnectionPool.from_url(REDIS_URL)
    HUEY = {
        "immediate": False,
        "connection": {
            "connection_pool": pool,
        },
        "consumer": {
            "workers": WORKER_COUNT,
            "worker_type": "thread",
        },
    }

GEOIP_PATH = options['GEOIP_PATH']

# binding options if running server
# listen on file descriptor
LISTEN_FD = options['LISTEN_FD']

# listen on host and port
LISTEN_HOST = options['LISTEN_HOST']
LISTEN_PORT = options['LISTEN_PORT']

# listen on unix socket
LISTEN_SOCKET = options['LISTEN_SOCKET']

LISTEN_SERVER = options['LISTEN_SERVER']

# how many workers (uvicorn)
LISTEN_CONCURRENCY = int(options['LISTEN_CONCURRENCY'])

# twisted endpoint (for daphne)
LISTEN_ENDPOINT = options['LISTEN_ENDPOINT']


# If you have the email_reply_trimmer_service running, set this to 'http://localhost:4567/trim' (or similar)
# https://github.com/yunity/email_reply_trimmer_service
EMAIL_REPLY_TRIMMER_URL = options['EMAIL_REPLY_TRIMMER_URL']

if MODE == 'prod':
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '%(levelname)s %(asctime)s %(module)s '
                          '%(process)d %(thread)d %(message)s'
            },
        },
        'handlers': {
            'sentry': {
                'level': 'WARNING',
                'class': 'raven.contrib.django.raven_compat.handlers.SentryHandler',
            },
            'console': {
                'level': 'WARNING',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose'
            }

        },
        'loggers': {
            'raven': {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': False,
            },
            'sentry.errors': {
                'level': 'WARNING',
                'handlers': ['console'],
                'propagate': False,
            },
            'django': {  # Disable django admin email logging by overriding
                'level': 'ERROR',
                'handlers': ['sentry'],
            },
        },
        'root': {  # log everything unconfigured as error
            'level': 'ERROR',
            'handlers': ['sentry'],
        },
    }

# NB: Keep this as the last line, and keep
# local_settings.py out of version control
try:
    from .local_settings import *  # noqa
except ImportError:
    pass
