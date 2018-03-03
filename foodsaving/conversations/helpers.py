import json

# load list of lists of alternative names of emojis
# gathered here:
# https://github.com/markdown-it/markdown-it-emoji/ (continue)
#    blob/f1bc7217e9eb4d954c145faf316718e263778e34/lib/data/full.json
with open('foodsaving/conversations/emoji_names.json') as json_data:
    emojis = json.load(json_data)

"""
# flattened emoji list as expected
EMOJI_LIST = [item[0] for item in emojis]


def isEmojiName(name: str) -> bool:
    "Find out whether name is a name of a supported emoji"

    return name in EMOJI_LIST
"""


def normalizeEmojiName(name: str) -> str:
    "Return a normalized name of emoji (important when the same emoji has multiple names)"

    for ls in emojis:
        if name in ls:
            return ls[0]
    # when not found, raise error
    raise Exception('not found')
