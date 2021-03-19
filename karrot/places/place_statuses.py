from django.utils.translation import gettext_lazy as _

# A list of translatable names that groups might use
# not sure if they should be more made more standard...
translatable_names = {
    'Created': _('Just created'),
    'Negotiating': _('Negotiating'),
    # this is actually the value for "active", should handle that in the data migration
    'Active': _('Active'),
    'Declined': _('Declined'),
    'Archived': _('Archived'),
}

# "ACTIVE": "Co-operating",
# "ARCHIVED": "Archived",
# "CREATED": "Just created",
# "DECLINED": "Don't want to cooperate",
# "NEGOTIATING": "Negotiating"

# CREATED = 'created'
# NEGOTIATING = 'negotiating'
# ACTIVE = 'active'
# DECLINED = 'declined'
# ARCHIVED = 'archived'

# Default types that will be created for new groups
# (in the future this would be more customizable)

default_place_statuses = {
    'Created': {
        'has_activities': False,
        'colour': '9E9E9E',  # quasar 'grey' rgb(158, 158, 158),
        'category': 'inactive',
    },
    'Negotiating': {
        'has_activities': False,
        'colour': '2196F3',  # quasar 'blue' rgb(33, 150, 243)
        'category': 'inactive',
    },
    'Active': {
        'has_activities': True,
        'colour': '21BA45',  # quasar 'positive' rgb(33, 186, 69)
        'category': 'active',
    },
    'Declined': {
        'has_activities': False,
        'colour': 'DB2828',  # quasar 'negative' rgb(219, 40, 40)
        'category': 'inactive',
    },
    'Archived': {
        'has_activities': False,
        'colour': '9E9E9E',  # quasar 'grey' rgb(158, 158, 158)
        'category': 'archived',
    }
}
