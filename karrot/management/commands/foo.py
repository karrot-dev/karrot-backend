from django.core.management import BaseCommand
from rest_framework import serializers


class FooSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.update({
            'name': serializers.CharField(),
        })
        print('fields', self.fields)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class Command(BaseCommand):
    def handle(self, *args, **options):
        data = {'name': 'Peter'}
        foo = FooSerializer(data=data)
        if foo.is_valid():
            print(foo.data)
        else:
            print('invalid!', foo.error_messages)
