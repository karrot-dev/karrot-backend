# every group member must have this, enforced by db constraint
GROUP_MEMBER = 'member'

# auto-managed role, for when 'member' is their only other role (TODO maybe plus a time constraint one day?)
GROUP_NEWCOMER = 'newcomer'

# unused, probably can remove at some point
GROUP_AGREEMENT_MANAGER = 'agreement_manager'

# trust-based built-in role, for giving permissions to edit group
GROUP_EDITOR = 'editor'
