from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.serializers import ModelSerializer

from karrot.history.models import History, HistoryTypus
from karrot.agreements.models import Agreement


class AgreementHistorySerializer(ModelSerializer):
    class Meta:
        model = Agreement
        fields = '__all__'


class AgreementSerializer(ModelSerializer):
    class Meta:
        model = Agreement
        fields = [
            'id',
            'title',
            'summary',
            'content',
            'active_from',
            'active_to',
            'review_at',
            'group',
            'created_by',
            'last_changed_by',
        ]
        read_only_fields = [
            'last_changed_by',
        ]

    def validate_group(self, group):
        if self.instance is not None:
            raise ValidationError('You cannot change the group')
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied('You are not a member of this group.')
        if not group.is_editor(self.context['request'].user):
            raise PermissionDenied('You need to be a group editor')
        return group

    @transaction.atomic
    def save(self, **kwargs):
        current_user = self.context['request'].user
        extra_kwargs = dict(last_changed_by=current_user)
        if self.instance is None:
            extra_kwargs.update(created_by=current_user)
        return super().save(**kwargs, **extra_kwargs)

    def create(self, validated_data):
        agreement = super().create(validated_data)
        History.objects.create(
            typus=HistoryTypus.AGREEMENT_CREATE,
            group=agreement.group,
            agreement=agreement,
            users=[
                self.context['request'].user,
            ],
            payload=self.initial_data,
            after=AgreementHistorySerializer(agreement).data,
        )
        return agreement

    def update(self, agreement, validated_data):
        before_data = AgreementHistorySerializer(agreement).data
        agreement = super().update(agreement, validated_data)
        History.objects.create(
            typus=HistoryTypus.AGREEMENT_MODIFY,
            group=agreement.group,
            agreement=agreement,
            users=[
                self.context['request'].user,
            ],
            payload=self.initial_data,
            before=before_data,
            after=AgreementHistorySerializer(agreement).data,
        )
        return agreement
