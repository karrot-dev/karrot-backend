from django.utils.translation import gettext_lazy as _

# A list of translatable names that groups might use
translatable_names = {
    'Unspecified': _('Unspecified'),
    'Store': _('Store'),
    'Sharing point': _('Sharing point'),
    'Meeting place': _('Meeting place'),
    'Restaurant': _('Restaurant'),
    'Market': _('Market'),
}

# Default types that will be created for new groups
default_place_types = {
    'Unspecified': {
        'icon': 'fas fa-map-marker',
    },
}
