import random
import re
import string

import unidecode
from django.db import migrations, models, IntegrityError, transaction
from django.db.models import Max, F
from django.db.models.functions import Coalesce

USERNAME_RE = re.compile(r'[a-zA-Z0-9_\-.]+')
USERNAME_INVALID_CHARS_RE = re.compile(r'[^a-zA-Z0-9_\-.]')
EMAIL_SUFFIX_RE = re.compile(r'@.+')

def try_options(user, options, n=None):
    for option in options:
        try:
            user.username = option + (str(n) if n else '')
            with transaction.atomic():
                user.save()
            return
        except IntegrityError:
            continue
    n = n + 1 if n else 1
    if n > 1000:
        raise Exception('I give up!')
    return try_options(user, options, n)


def random_username():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def convert(text):
    # has various caveats, does not do locale-aware conversion
    # e.g. German "ä" goes to "a" not "ae"
    # https://pypi.org/project/Unidecode/ explains why it's difficult
    # it should be fine for our purposes :)
    return unidecode.unidecode(text.lower())


def conform(str):
    return USERNAME_INVALID_CHARS_RE.sub('_', EMAIL_SUFFIX_RE.sub('', str.strip()))


def fix_usernames(apps, schema_editor):
    User = apps.get_model('users', 'User')

    # prefer users that were seen recently, then ones that logged in recently, finally fall back to creation date
    users = User.objects.annotate(lastseen_at=Max(F('groupmembership__lastseen_at')))
    for user in users.order_by(Coalesce('lastseen_at', 'last_login').desc(nulls_last=True), '-created_at'):
        if not USERNAME_RE.fullmatch(user.username):
            options = []
            if user.username:
                options.append(conform(convert(user.username)))
            if user.display_name:
                options.append(conform(convert(user.display_name).split(' ')[0]))
                options.append(conform(convert(user.display_name).replace(' ', '')))
            if user.email:
                options.append(conform(convert(user.email).split('@')[0]))
            if not options:
                options.append(random_username())
            try_options(user, options)


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0026_alter_user_username'),
    ]

    operations = [
        migrations.RunPython(fix_usernames, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
