from karrot.utils.influxdb_utils import write_points


def login_failed(email):
    write_points([{
        'measurement': 'django_auth_user_login_failed',  # mimic existing stats from django-influxdb-metrics
        'fields': {
            'value': 1,
            'email': email,
        },
    }])


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
