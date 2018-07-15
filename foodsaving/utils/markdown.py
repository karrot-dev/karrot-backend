import bleach
import markdown
import pymdownx
import pymdownx.emoji
import pymdownx.superfences
from bleach_whitelist.bleach_whitelist import markdown_attrs, markdown_tags
from django.utils.text import Truncator


def render(text, truncate_words=None):
    html = markdown.markdown(text, extensions=[
        pymdownx.emoji.EmojiExtension(emoji_index=pymdownx.emoji.twemoji),
        'pymdownx.superfences',
        'pymdownx.magiclink',
        'markdown.extensions.nl2br',
    ])
    markdown_attrs['img'].append('class')
    markdown_tags.append('pre')
    clean_html = bleach.clean(html, markdown_tags, markdown_attrs)

    if truncate_words:
        clean_html = Truncator(clean_html).words(num=truncate_words, html=True)

    return clean_html
