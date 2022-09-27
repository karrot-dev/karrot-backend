from rest_framework.serializers import ModelSerializer

from karrot.agreements.models import Agreement


class AgreementSerializer(ModelSerializer):
    class Meta:
        model = Agreement
        fields = [
            'id',
            'title',
            'summary',
            'content',
            'valid_from',
            'valid_to',
        ]
