from django.utils.translation import gettext_lazy as _
from fractional_indexing import generate_key_between

# A list of translatable names that groups might use
translatable_names = {
    'Created': _('Created'),
    'Negotiating': _('Negotiating'),
    'Active': _('Active'),
    'Declined': _('Declined'),
}

_last_order = None


def next_order():
    global _last_order
    order = generate_key_between(_last_order, None)
    _last_order = order
    return order


# Default types that will be created for new groups
# (in the future this would be more customizable)
default_place_statuses = {
    'Created': {
        'name_is_translatable': True,
        'colour': '9e9e9e',
        'is_visible': True,
        'order': next_order(),
    },
    'Negotiating': {
        'name_is_translatable': True,
        'colour': '2196f3',
        'is_visible': True,
        'order': next_order(),
    },
    'Active': {
        'name_is_translatable': True,
        'colour': '21BA45',
        'is_visible': True,
        'order': next_order(),
    },
    'Declined': {
        'name_is_translatable': True,
        'colour': 'DB2828',
        'is_visible': False,
        'order': next_order(),
    },
}
