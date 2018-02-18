from anymail.message import AnymailMessage
from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import transaction, models
from django.db.models import EmailField, BooleanField, TextField, CharField, DateTimeField, ForeignKey, SmallIntegerField, ManyToManyField
from django.template.loader import render_to_string
from django.utils.translation import ugettext as _
from versatileimagefield.fields import VersatileImageField
from django.utils import timezone
from django.core.exceptions import ValidationError

from foodsaving.base.base_models import BaseModel, LocationModel
from foodsaving.userauth.models import VerificationCode

MAX_DISPLAY_NAME_LENGTH = 80


class UserManager(BaseUserManager):
    use_in_migrations = True

    @transaction.atomic
    def _create_user(self, email, password, display_name=None, is_active=True, **extra_fields):
        """ Creates and saves a user with the given username, email and password.

        """
        email = self._validate_email(email)
        extra_fields['unverified_email'] = email

        user = self.model(
            email=email,
            is_active=is_active,
            display_name=display_name,
            **extra_fields)
        user.set_password(password)
        user.save()
        user._send_welcome_mail()
        return user

    def filter_by_similar_email(self, email):
        return self.filter(email__iexact=email)

    def active(self):
        return self.filter(deleted=False, is_active=True)

    def get_by_natural_key(self, email):
        """
        As we don't allow sign-ups with similarly cased email addresses,
        we can allow users to login with case spelling mistakes
        """
        return self.get(email__iexact=email)

    def _validate_email(self, email):
        if email is None:
            raise ValueError('The email field must be set')
        return self.normalize_email(email)

    def create_user(self, email=None, password=None, display_name=None,
                    **extra_fields):
        return self._create_user(email, password, display_name, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        user = self._create_user(email, password, email, **extra_fields)
        user.is_superuser = True
        user.is_staff = True
        user.save()
        return user


class User(AbstractBaseUser, BaseModel, LocationModel):
    email = EmailField(unique=True, null=True)
    is_active = BooleanField(default=True)
    is_staff = BooleanField(default=False)
    is_superuser = BooleanField(default=False)
    display_name = CharField(max_length=settings.NAME_MAX_LENGTH)
    description = TextField(blank=True)
    language = CharField(max_length=7, default='en')
    mail_verified = BooleanField(default=False)
    unverified_email = EmailField(null=True)

    deleted = BooleanField(default=False)
    deleted_at = DateTimeField(default=None, null=True)
    current_group = ForeignKey('groups.Group', blank=True, null=True, on_delete=models.SET_NULL)
    trusts = ManyToManyField('users.User', through='Trust', through_fields=('sender', 'reciever'))

    photo = VersatileImageField(
        'Photo',
        upload_to='user__photos',
        null=True,
    )

    objects = UserManager()

    USERNAME_FIELD = 'email'

    def get_full_name(self):
        return self.display_name

    def get_short_name(self):
        return self.display_name

    def delete_photo(self):
        # Deletes Image Renditions
        self.photo.delete_all_created_images()
        # Deletes Original Image
        self.photo.delete(save=False)

    @transaction.atomic
    def verify_mail(self):
        VerificationCode.objects.filter(user=self, type=VerificationCode.EMAIL_VERIFICATION).delete()
        self.email = self.unverified_email
        self.mail_verified = True
        self.save()

    @transaction.atomic
    def _unverify_mail(self):
        VerificationCode.objects.filter(user=self, type=VerificationCode.EMAIL_VERIFICATION).delete()
        VerificationCode.objects.create(user=self, type=VerificationCode.EMAIL_VERIFICATION)
        self.mail_verified = False
        self.save()

    @transaction.atomic
    def update_email(self, unverified_email):
        self.unverified_email = unverified_email
        self._send_mail_change_notification()
        self.send_new_verification_code()

    def update_language(self, language):
        self.language = language

    def _send_mail_change_notification(self):
        context = {
            'user': self,
        }

        AnymailMessage(
            subject=render_to_string('changemail_notice-subject.jinja').replace('\n', ''),
            body=render_to_string('changemail_notice-body-text.jinja', context),
            to=[self.email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            track_clicks=False,
            track_opens=False
        ).send()

    def _send_welcome_mail(self):
        self._unverify_mail()

        url = '{hostname}/#/verify-mail?key={code}'.format(
            hostname=settings.HOSTNAME,
            code=VerificationCode.objects.get(user=self, type=VerificationCode.EMAIL_VERIFICATION).code
        )

        context = {
            'user': self,
            'url': url,
        }

        AnymailMessage(
            subject=render_to_string('mailverification-subject.jinja').replace('\n', ''),
            body=render_to_string('mailverification-body-text.jinja', context),
            to=[self.unverified_email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            track_clicks=False,
            track_opens=False
        ).send()

    @transaction.atomic
    def send_new_verification_code(self):
        self._unverify_mail()

        url = '{hostname}/#/verify-mail?key={code}'.format(
            hostname=settings.HOSTNAME,
            code=VerificationCode.objects.get(user=self, type=VerificationCode.EMAIL_VERIFICATION).code
        )

        context = {
            'user': self,
            'url': url,
        }

        AnymailMessage(
            subject=render_to_string('send_new_verification_code-subject.jinja').replace('\n', ''),
            body=render_to_string('send_new_verification_code-body-text.jinja', context),
            to=[self.unverified_email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            track_clicks=False,
            track_opens=False
        ).send()

    @transaction.atomic
    def reset_password(self):
        new_password = User.objects.make_random_password(length=20)
        self.set_password(new_password)
        self.save()

        AnymailMessage(
            subject=_('New password'),
            body=_('Here is your new temporary password: {}. ' +
                   'You can use it to login. Please change it soon.').format(new_password),
            to=[self.email],
            from_email=settings.DEFAULT_FROM_EMAIL,
            track_clicks=False,
            track_opens=False
        ).send()

    def has_perm(self, perm, obj=None):
        # temporarily only allow access for admins
        return self.is_superuser

    def has_module_perms(self, app_label):
        # temporarily only allow access for admins
        return self.is_superuser

    def trust_by(self, loggedinUser):
        if self.id == loggedinUser.id:
            # TODO: maybe wrong position for such validations?
            raise ValidationError("you don't have to mark explicitly, that you trust yourself")

        trust = self.trust_recieved.filter(sender=loggedinUser)
        if not trust.exists():

            # rate limits
            # TODO: maybe wrong position for such validations?
            week = timezone.now()-timezone.timedelta(days=7)
            day = timezone.now()-timezone.timedelta(days=1)
            month = timezone.now()-timezone.timedelta(days=30)
            trustsDay = loggedinUser.trust_sent.filter(created_at__gt=day).count()
            if trustsDay > settings.TRUST_RATE_LIMIT_DAY:
                raise ValidationError("max {} trusts per day".format(settings.TRUST_RATE_LIMIT_DAY))

            trustsWeek = loggedinUser.trust_sent.filter(created_at__gt=week).count()
            if trustsWeek > settings.TRUST_RATE_LIMIT_WEEK:
                raise ValidationError("max {} trusts per week".format(settings.TRUST_RATE_LIMIT_WEEK))

            trustsMonth = loggedinUser.trust_sent.filter(created_at__gt=month).count()
            if trustsMonth > settings.TRUST_RATE_LIMIT_DAY:
                raise ValidationError("max {} trusts per month".format(settings.TRUST_RATE_LIMIT_MONTH))

            Trust.objects.create(sender=loggedinUser, reciever=self)
        else:
            trust[0].created_at = timezone.now()            
            trust[0].save()
    
    def untrust_by(self, loggedinUser):
        trust = self.trust_recieved.get(sender=loggedinUser)
        if trust:
            trust.delete()

    def get_trust_by(self, loggedinUser):
        minimum_creation_date = timezone.now()-timezone.timedelta(days=settings.TRUST_EXPIRE_TIME_DAYS)
        trusts = self.trust_recieved.filter(sender=loggedinUser, created_at__gt=minimum_creation_date)
        if trusts.exists():
            return trusts.first()
        else:
            return None


class Trust(BaseModel):
    sender = ForeignKey(settings.AUTH_USER_MODEL, related_name='trust_sent', on_delete=models.CASCADE)
    reciever = ForeignKey('users.User', related_name='trust_recieved', on_delete=models.CASCADE)
    level = SmallIntegerField(default=5)
