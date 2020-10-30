from django.utils.translation import gettext_lazy as _

# A list of translatable names that groups might use
translatable_names = {
    'Meeting': _('Meeting'),
    'Pickup': _('Pickup'),
    'Distribution': _('Distribution'),
    'Event': _('Event'),
    'Activity': _('Activity'),
}

# Default types that will be created for new groups
# (in the future this would be more customizable)
default_activity_types = {
    'Meeting': {
        'colour': 'AD1457',
        'icon': 'fas fa-handshake',
        'feedback_icon': 'fas fa-reply',
        'has_feedback': True,
        'has_feedback_weight': False,
    },
    'Pickup': {
        'colour': '007700',
        'icon': 'fas fa-shopping-basket',
        'feedback_icon': 'fas fa-balance-scale',
        'has_feedback': True,
        'has_feedback_weight': True,
    },
    'Distribution': {
        'colour': '1976D2',
        'icon': 'fas fa-people-arrows',
        'feedback_icon': 'fas fa-reply',
        'has_feedback': True,
        'has_feedback_weight': False,
    },
    'Event': {
        'colour': 'EF6C00',
        'icon': 'fas fa-calendar-check',
        'feedback_icon': 'fas fa-reply',
        'has_feedback': True,
        'has_feedback_weight': False,
    },
}
