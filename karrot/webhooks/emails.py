from karrot.utils.email_utils import prepare_email


def prepare_incoming_email_rejected_email(user, content):
    return prepare_email(
        template='incoming_email_rejected',
        user=user,
        context={'content': content},
    )
