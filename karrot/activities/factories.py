from datetime import timedelta
from random import randint

from dateutil.relativedelta import relativedelta
from django.utils import timezone
from factory import SubFactory, LazyFunction, LazyAttribute, post_generation, Sequence, SelfAttribute
from factory.django import DjangoModelFactory

from karrot.activities.models import (
    Activity as ActivityModel,
    ActivitySeries as ActivitySeriesModel,
    Feedback as FeedbackModel,
    to_range,
    ActivityType,
)
from karrot.places.factories import PlaceFactory
from karrot.utils.tests.fake import faker


def in_one_day():
    return to_range(timezone.now() + timedelta(days=1))


class ActivityTypeFactory(DjangoModelFactory):
    class Meta:
        model = ActivityType

    name = Sequence(lambda n: " ".join(["ActivityType", str(n), faker.first_name()]))


class ActivityFactory(DjangoModelFactory):
    class Meta:
        model = ActivityModel

    @post_generation
    def participant_types(self, created, participant_types, **kwargs):
        if not created:
            return
        if not participant_types:
            # default set...
            participant_types = [
                {
                    "role": "member",
                    "max_participants": 5,
                },
            ]
        for participant_type in participant_types:
            self.participant_types.create(**participant_type)

    @post_generation
    def participants(self, created, participants, **kwargs):
        if not created:
            return
        if participants:
            for user in participants:
                self.add_participant(user)

    activity_type = SubFactory(ActivityTypeFactory, group=SelfAttribute("..place.group"))
    place = SubFactory(PlaceFactory)
    date = LazyFunction(in_one_day)


class ActivitySeriesFactory(DjangoModelFactory):
    class Meta:
        model = ActivitySeriesModel

    @post_generation
    def participant_types(self, created, participant_types, **kwargs):
        if not created:
            return
        if not participant_types:
            # default set...
            participant_types = [
                {
                    "role": "member",
                    "max_participants": 5,
                },
            ]
        for participant_type in participant_types:
            self.participant_types.create(**participant_type)

    @post_generation
    def update_activities(self, created, ignored, **kwargs):
        self.update_activities()

    activity_type = SubFactory(ActivityTypeFactory, group=SelfAttribute("..place.group"))
    place = SubFactory(PlaceFactory)
    start_date = LazyAttribute(lambda _: timezone.now().replace(second=0, microsecond=0) + relativedelta(minutes=15))
    rule = "FREQ=WEEKLY"


class FeedbackFactory(DjangoModelFactory):
    class Meta:
        model = FeedbackModel

    comment = LazyAttribute(lambda x: faker.sentence(nb_words=4))
    weight = LazyAttribute(lambda x: randint(0, 32))
