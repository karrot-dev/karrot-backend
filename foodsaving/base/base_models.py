from django.contrib.postgres.fields import DateTimeRangeField
from django.db import connection
from django.db.models import Model, AutoField, Field, DateTimeField, TextField, FloatField
from django.db.models.fields.related import RelatedField
from django.utils import timezone
from psycopg2.extras import DateTimeTZRange, register_range


class NicelyFormattedModel(Model):
    class Meta:
        abstract = True

    def _get_explicit_field_names(self):
        """
        :rtype: list
        """
        return [
            field.name for field in self._meta.get_fields()
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
        columns = ', '.join('{}="{}"'.format(field, value) for field, value in self.to_dict().items())
        return '{}({})'.format(model, columns)


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


class CustomDateTimeTZRange(DateTimeTZRange):
    """
    Similar to psycopg2.extras.DateTimeTZRange but with extra helpers
    """

    @property
    def start(self):
        return self.lower

    @property
    def end(self):
        return self.upper

    def __add__(self, delta):
        return CustomDateTimeTZRange(
            self.lower + delta if self.lower else None, self.upper + delta if self.upper else None
        )

    def __sub__(self, delta):
        return CustomDateTimeTZRange(
            self.lower - delta if self.lower else None, self.upper - delta if self.upper else None
        )

    def as_list(self):
        return [self.start, self.end]


class CustomDateTimeRangeField(DateTimeRangeField):
    range_type = CustomDateTimeTZRange


def register_custom_date_time_tz_range():
    connection.ensure_connection()
    register_range('pg_catalog.tstzrange', CustomDateTimeTZRange, connection.connection, True)
    connection.close()  # don't leave connection lying around as we might be actually running the app now


register_custom_date_time_tz_range()
