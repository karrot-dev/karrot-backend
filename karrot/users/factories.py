from django.contrib.auth import get_user_model
from factory import CREATE_STRATEGY, LazyAttribute, PostGeneration, Sequence
from factory.django import DjangoModelFactory

from karrot.utils.tests.fake import faker


def set_password(obj, *args, **kwargs_):
    if hasattr(obj, 'set_password'):
        obj.set_password(obj.display_name)
    else:
        print('HMMM', obj)


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()
        strategy = CREATE_STRATEGY

    is_active = True
    is_staff = False
    username = LazyAttribute(lambda _: faker.user_name())
    display_name = LazyAttribute(lambda _: faker.name())
    email = Sequence(lambda n: str(n) + faker.email())
    description = LazyAttribute(lambda _: faker.text())

    # Use display_name as password, as it is readable
    password = PostGeneration(set_password)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        manager = cls._get_manager(model_class)
        user = manager.create_user(*args, **kwargs)
        return user


class VerifiedUserFactory(UserFactory):
    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        user = super()._create(model_class, *args, **kwargs)
        user.verify_mail()
        return user
