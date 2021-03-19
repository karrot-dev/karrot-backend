from django.utils.translation import gettext_lazy as _

# A list of translatable names that groups might use
translatable_names = {
    'Store': _('Store'),
    'Place': _('Place'),
    # TODO: more?
}

# Default types that will be created for new groups
# (in the future this would be more customizable)
default_place_types = {
    'Store': {
        'icon': 'fas fa-shopping-cart',
    },
    # TODO: also a generic type?
}
