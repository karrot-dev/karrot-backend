from anymail.exceptions import AnymailAPIError
from django.utils import timezone
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.validators import UniqueTogetherValidator

from foodsaving.invitations.models import Invitation


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ['id', 'email', 'group', 'invited_by', 'expires_at', 'created_at']
        extra_kwargs = {'invited_by': {'read_only': True}}
        validators = [
            UniqueTogetherValidator(
                queryset=Invitation.objects.filter(expires_at__gte=timezone.now()),
                fields=('email', 'group'),
                message=_(
                    'An invitation has already been sent to this e-mail address, you can only resend after one hour!'
                )
            )
        ]

    def validate_group(self, group):
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied(_('You are not a member of this group.'))
        if not group.is_editor(self.context['request'].user):
            raise PermissionDenied(_('You need to be a group editor'))
        return group

    def validate(self, attrs):
        if attrs['group'].members.filter(email=attrs['email']).exists():
            raise serializers.ValidationError(_('User is already member of group'))
        return attrs

    def create(self, validated_data):
        validated_data['invited_by'] = self.context['request'].user
        try:
            return self.Meta.model.objects.create_and_send(**validated_data)
        except AnymailAPIError:
            raise serializers.ValidationError(_('Email could not be sent'))


class InvitationAcceptSerializer(serializers.Serializer):
    def update(self, invitation, validated_data):
        invitation.accept(self.context['request'].user)
        return invitation


class InvitationResendEmailSerializer(serializers.Serializer):
    from datetime import timedelta

    created_at = serializers.DateTimeField()

    def validate(self, attrs):
        if not timezone.now() >= attrs['created_at'] + self.timedelta(hours=1):
            raise serializers.ValidationError(
                _('An invitation has already been sent to this e-mail address, you can only resend after one hour!')
            )
        return attrs

    def update(self, invitation, validated_data):
        invitation.resend_invitation_email()
        return invitation
