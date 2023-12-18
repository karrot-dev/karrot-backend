from django.contrib.postgres.fields import DateTimeRangeField
from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.db.backends.signals import connection_created
from django.db.models import Model, AutoField, Field, DateTimeField, TextField, FloatField, Func
from django.db.models.fields.related import RelatedField
from django.dispatch import receiver
from django.utils import timezone
from psycopg.types.range import TimestampTZRangeLoader


class NicelyFormattedModel(Model):
    class Meta:
        abstract = True

    def _get_explicit_field_names(self):
        """
        :rtype: list
        """
        return [
            field.name
            for field in self._meta.get_fields()
            if isinstance(field, Field) and not isinstance(field, RelatedField)
        ]

    def to_dict(self):
        """
        :rtype: dict
        """
        fields = self._get_explicit_field_names()
        return {field: getattr(self, field) for field in fields if getattr(self, field)}

    def __repr__(self):
        model = str(self.__class__.__name__)
        columns = ", ".join('{}="{}"'.format(field, value) for field, value in self.to_dict().items())
        return "{}({})".format(model, columns)


class BaseModel(NicelyFormattedModel):
    class Meta:
        abstract = True

    id = AutoField(primary_key=True)
    created_at = DateTimeField(default=timezone.now)


class UpdatedAtMixin(Model):
    class Meta:
        abstract = True

    updated_at = DateTimeField(auto_now=True)


class LocationModel(Model):
    class Meta:
        abstract = True

    address = TextField(null=True)
    latitude = FloatField(null=True)
    longitude = FloatField(null=True)


class Tstzrange(Func):
    function = "tstzrange"


class CustomDateTimeTZRange(DateTimeTZRange):
    """
    Similar to psycopg.types.range.Range but with extra helpers
    """

    @property
    def start(self):
        return self.lower

    @property
    def end(self):
        return self.upper

    def __add__(self, delta):
        return CustomDateTimeTZRange(
            self.lower + delta if self.lower else None,
            self.upper + delta if self.upper else None,
            self.bounds,
        )

    def __sub__(self, delta):
        return CustomDateTimeTZRange(
            self.lower - delta if self.lower else None,
            self.upper - delta if self.upper else None,
            self.bounds,
        )

    def as_list(self):
        return [self.start, self.end]

    def astimezone(self, tz):
        return CustomDateTimeTZRange(
            self.lower.astimezone(tz) if self.lower else None,
            self.upper.astimezone(tz) if self.upper else None,
            self.bounds,
        )


class CustomDateTimeRangeField(DateTimeRangeField):
    range_type = CustomDateTimeTZRange


class CustomTimestampTZRangeLoader(TimestampTZRangeLoader):
    def load(self, data):
        range = super().load(data)
        return CustomDateTimeTZRange(range.lower, range.upper, range.bounds)


@receiver(connection_created)
def register_custom_date_time_tz_range(sender, connection, **kwargs):
    psycopg_connection = connection.connection
    psycopg_connection.adapters.register_loader("tstzrange", CustomTimestampTZRangeLoader)
