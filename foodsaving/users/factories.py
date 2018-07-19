from django.contrib.auth import get_user_model
from factory import DjangoModelFactory, CREATE_STRATEGY, LazyAttribute, PostGeneration
from foodsaving.utils.tests.fake import faker


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()
        strategy = CREATE_STRATEGY

    is_active = True
    is_staff = False
    display_name = LazyAttribute(lambda _: faker.name())
    email = LazyAttribute(lambda _: faker.email())
    description = LazyAttribute(lambda _: faker.text())

    # Use display_name as password, as it is readable
    password = PostGeneration(lambda obj, *args, **kwargs: obj.set_password(obj.display_name))

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
