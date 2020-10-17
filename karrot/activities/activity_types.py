from django.utils.translation import gettext as _

default_activity_types = {
    'Pickup': {
        'name': _('Pickup'),
        'colour': '007700',
        'icon': 'fas fa-shopping-basket',
        'feedback_icon': 'fas fa-balance-scale',
        'has_feedback': True,
        'has_feedback_weight': True,
    },
    'Task': {
        'name': _('Task'),
        'colour': '283593',
        'icon': 'fas fa-check-square',
        'feedback_icon': 'fas fa-reply',
        'has_feedback': True,
        'has_feedback_weight': False,
    },
    'Meeting': {
        'name': _('Meeting'),
        'colour': 'AD1457',
        'icon': 'fas fa-handshake',
        'feedback_icon': 'fa-reply',
        'has_feedback': True,
        'has_feedback_weight': False,
    },
}
