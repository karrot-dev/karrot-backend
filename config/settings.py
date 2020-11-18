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
from karrot.groups import themes

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Karrot constants

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

KARROT_LOGO = 'https://user-images.githubusercontent.com/31616/36565633-517373a4-1821-11e8-9948-5bf6887c667e.png'

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

REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://{}:6379/0".format(REDIS_HOST),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"

WSGI_APPLICATION = 'config.wsgi.application'

# don't send out email by default, override in local_settings.py
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
            "hosts": [(REDIS_HOST, 6379)],
            "capacity": 150,
        },
    },
}

ASGI_APPLICATION = 'karrot.subscriptions.routing.application'

# Default dummy settings, please override in local_settings.py
DEFAULT_FROM_EMAIL = "testing@example.com"
SPARKPOST_RELAY_DOMAIN = 'replies.karrot.localhost'
HOSTNAME = 'http://localhost:8000'
SITE_NAME = 'karrot local development'
MEDIA_ROOT = './uploads/'
MEDIA_URL = '/media/'
INFLUXDB_DISABLED = True
INFLUXDB_HOST = ''
INFLUXDB_PORT = ''
INFLUXDB_USER = ''
INFLUXDB_PASSWORD = ''
INFLUXDB_DATABASE = ''
INFLUXDB_TAGS_HOST = ''
INFLUXDB_TIMEOUT = 5
INFLUXDB_USE_CELERY = False
INFLUXDB_USE_THREADING = True

HUEY = {
    'immediate': True,
}

GEOIP_PATH = os.path.join(BASE_DIR, 'maxmind-data')

# If you have the email_reply_trimmer_service running, set this to 'http://localhost:4567/trim' (or similar)
# https://github.com/yunity/email_reply_trimmer_service
EMAIL_REPLY_TRIMMER_URL = None

# NB: Keep this as the last line, and keep
# local_settings.py out of version control
try:
    from .local_settings import *  # noqa
except ImportError:
    raise Exception(
        "config/local_settings.py is missing! Copy the provided example file and adapt it to your own config."
    )
