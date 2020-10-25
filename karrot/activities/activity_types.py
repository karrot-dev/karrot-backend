from django.utils.translation import gettext_lazy as _

# A list of translatable names that groups might use
translatable_names = {
    'Pickup': _('Pickup'),
    'Task': _('Task'),
    'Meeting': _('Meeting'),
}

# Default types that will be created for new groups
# (in the future this would be more customizable)
default_activity_types = {
    'Pickup': {
        'colour': '007700',
        'icon': 'fas fa-shopping-basket',
        'feedback_icon': 'fas fa-balance-scale',
        'has_feedback': True,
        'has_feedback_weight': True,
    },
    'Task': {
        'colour': '283593',
        'icon': 'fas fa-check-square',
        'feedback_icon': 'fas fa-reply',
        'has_feedback': True,
        'has_feedback_weight': False,
    },
    'Meeting': {
        'colour': 'AD1457',
        'icon': 'fas fa-handshake',
        'feedback_icon': 'fa-reply',
        'has_feedback': True,
        'has_feedback_weight': False,
    },
}
