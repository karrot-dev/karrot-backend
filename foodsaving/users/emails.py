from foodsaving.utils.email_utils import prepare_email
from foodsaving.utils.frontend_urls import user_delete_url, user_passwordreset_url, user_emailverification_url


def prepare_accountdelete_request_email(user, verification_code):
    return prepare_email(
        template='accountdelete_request',
        user=user,
        context={'url': user_delete_url(verification_code.code)},
    )


def prepare_accountdelete_success_email(user):
    return prepare_email(
        template='accountdelete_success',
        user=user,
    )


def prepare_changemail_request_email(user, verification_code):
    return prepare_email(
        template='changemail_request',
        user=user,
        context={
            'url': user_emailverification_url(verification_code.code),
        },
        to=user.unverified_email,
    )


def prepare_changemail_success_email(user):
    return prepare_email(
        template='changemail_success',
        user=user,
    )


def prepare_passwordreset_request_email(user, verification_code):
    return prepare_email(
        template='passwordreset_request',
        user=user,
        context={'url': user_passwordreset_url(verification_code.code)},
    )


def prepare_passwordreset_success_email(user):
    return prepare_email(
        template='passwordreset_success',
        user=user,
    )


def prepare_signup_email(user, verification_code):
    return prepare_email(
        template='signup',
        user=user,
        context={'url': user_emailverification_url(verification_code.code)},
        to=user.unverified_email,
    )
