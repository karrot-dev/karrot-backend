from karrot.users.models import User
from karrot.utils.influxdb_utils import write_points


def login_successful():
    write_points([{
        'measurement': 'django_auth_user_login',  # mimic existing stats
        'fields': {
            'value': 1
        },
    }])


def login_failed(email):
    write_points([{
        'measurement': 'django_auth_user_login_failed',  # mimic existing stats
        'fields': {
            'value': 1,
            'email': email,
        },
    }])


def user_created():
    total = User.objects.all().count()
    data = [{
        'measurement': 'django_auth_user_create',
        'fields': {
            'value': 1,
        },
    }]
    write_points(data)

    data = [{
        'measurement': 'django_auth_user_count',
        'fields': {
            'value': total,
        },
    }]
    write_points(data)


def password_reset_requested():
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'password_reset_requested': 1,
        },
    }])


def password_reset_successful():
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'password_reset_successful': 1,
        },
    }])


def account_deletion_requested():
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'account_deletion_requested': 1,
        },
    }])


def account_deletion_successful():
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'account_deletion_successful': 1,
        },
    }])


def verification_code_failed(reason):
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'verification_code_{}'.format(reason): 1,
            'verification_code_failed': 1,
        },
    }])


def password_changed():
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'password_changed': 1,
        },
    }])


def email_changed():
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'email_changed': 1,
        },
    }])
