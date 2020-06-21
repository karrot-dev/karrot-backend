from django.conf import settings
from django.core.checks import Error, Warning, register


@register(deploy=True)
def deploy_settings_check(app_configs, **kwargs):
    errors = []
    if not settings.HOSTNAME.startswith("http"):
        errors.append(
            Error(
                "Missing scheme in HOSTNAME",
                hint="Configure a hostname that starts with a scheme (e.g. https)",
                obj=settings.HOSTNAME,
            )
        )
    if "<" in settings.DEFAULT_FROM_EMAIL or "@" not in settings.DEFAULT_FROM_EMAIL:
        errors.append(
            Error(
                "DEFAULT_FROM_EMAIL is not an pure e-mail address",
                hint="Make sure that it does not contain a name, instead use SITE_NAME for it",
                obj=settings.DEFAULT_FROM_EMAIL,
            )
        )
    if (
        not settings.ANYMAIL.get("POSTAL_API_KEY")
        or len(settings.ANYMAIL.get("POSTAL_API_KEY")) < 10
    ):
        errors.append(
            Error(
                "Missing ANYMAIL.POSTAL_API_KEY",
                hint="Needs a postal API key to send out e-mails",
            )
        )

    # Postal doesn't support webhook basic auth
    # if not settings.ANYMAIL.get('WEBHOOK_SECRET') or len(settings.ANYMAIL.get('WEBHOOK_SECRET')) < 5:
    #     errors.append(
    #         Error(
    #             'Missing ANYMAIL.WEBHOOK_SECRET',
    #             hint='Set it to a random string to secure the e-mail events webhook (for bounces etc)',
    #         )
    #     )
    if len(settings.SITE_NAME) > 40:
        errors.append(
            Warning(
                "SITE_NAME is quite long",
                hint="It will get used as default e-mail sender name, so better keep it short",
                obj=settings.SITE_NAME,
            )
        )

    return errors
