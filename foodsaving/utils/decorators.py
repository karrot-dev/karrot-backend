from django.db import transaction
from rest_framework import generics


class acquire_lock_before_actions(object):
    """
    Enable atomic transactions and select_for_update locks on each given action.
    Can be applied to subclasses of GenericAPIView, as we patch the action and get_queryset method
    """
    def __init__(self, *args):
        """Receive actions names as arguments"""
        self.actions = args

    def decorate_class(self, cls):
        for action in self.actions:
            """Enable atomic transaction"""
            decorated_action_handler = getattr(cls, action)
            setattr(cls, action, transaction.atomic(decorated_action_handler))

        decorated_get_queryset = cls.get_queryset

        def get_queryset(decorated_self, *args, **kwargs):
            """Apply select_for_update lock on queryset returned from get_queryset()"""
            qs = decorated_get_queryset(decorated_self, *args, **kwargs)
            if decorated_self.action in self.actions:
                qs = qs.select_for_update()
            return qs

        cls.get_queryset = get_queryset
        return cls

    def __call__(self, decorated):
        """decorator entry point, receives class to decorate"""
        if issubclass(decorated, generics.GenericAPIView):
            return self.decorate_class(decorated)
        raise TypeError('Can only decorate subclasses of GenericAPIView')
