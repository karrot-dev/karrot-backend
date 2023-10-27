from django.utils.translation import gettext_lazy as _

# A list of translatable names that groups might use
translatable_names = {
    # TODO: do we have these translations already?
    # ... can we just use frontend translations?
    # how does it all work!
    'Created': _('Created'),
    'Negotiating': _('Negotiating'),
    'Active': _('Active'),
    'Declined': _('Declined'),
}

# Default types that will be created for new groups
# (in the future this would be more customizable)
default_place_statuses = {
    'Created': {
        'colour': '9e9e9e',
    },
    'Negotiating': {
        'colour': '2196f3',
    },
    'Active': {
        'colour': '21BA45',
    },
    'Declined': {
        'colour': 'DB2828'
    },
}
