import os
from dotenv import load_dotenv

load_dotenv()

INSTALLED_APPS = (
    # Should be loaded first
    'channels',

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
    # can exclude the extensions if in an environment where the db user
    # does not have permission to install extensions
    # in that case you need to install them using another mechanism
    *(() if os.environ.get(
        'EXCLUDE_EXTENSION_MIGRATIONS',
    ) else 'karrot.dbextensions', ),
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
    'karrot.agreements.AgreementsConfig',
    'karrot.stats',
    'karrot.status.StatusConfig',
    'karrot.utils',

    # Django packages
    'django_extensions',
    'corsheaders',
    'rest_framework',
    'rest_framework.authtoken',
    'drf_spectacular',
    'anymail',
    'timezone_field',
    'django_jinja',
    'versatileimagefield',
    'huey.contrib.djhuey',
    'silk',
)
