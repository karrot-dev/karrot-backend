from rest_framework import serializers
from rest_framework.fields import SerializerMethodField

from foodsaving.activity.models import Activity, ActivityTypus


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Activity
        fields = ['id', 'date', 'typus', 'group', 'store', 'users', 'payload']

    typus = SerializerMethodField()

    def get_typus(self, obj):
        return ActivityTypus.name(obj.typus)
