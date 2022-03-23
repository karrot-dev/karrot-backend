import re

USERNAME_RE = re.compile(r'[a-zA-Z0-9_\-.]+')
USERNAME_MENTION_RE = re.compile(r'@([a-zA-Z0-9_\-.]+)')
