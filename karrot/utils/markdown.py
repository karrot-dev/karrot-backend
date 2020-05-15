import bleach
import markdown
from bleach_whitelist.bleach_whitelist import markdown_attrs, markdown_tags
from django.utils.text import Truncator
from markdown.extensions.nl2br import Nl2BrExtension
from pymdownx.emoji import EmojiExtension, twemoji
from pymdownx.magiclink import MagiclinkExtension
from pymdownx.superfences import SuperFencesCodeExtension
from pymdownx.tilde import DeleteSubExtension


def render(text, truncate_words=None):
    html = markdown.markdown(
        text,
        extensions=[
            EmojiExtension(emoji_index=twemoji),
            SuperFencesCodeExtension(),
            MagiclinkExtension(),
            DeleteSubExtension(subscript=False),
            Nl2BrExtension(),
        ]
    )
    markdown_attrs['img'].append('class')
    markdown_tags.append('pre')
    clean_html = bleach.clean(html, markdown_tags, markdown_attrs)

    if truncate_words:
        clean_html = Truncator(clean_html).words(num=truncate_words, html=True)

    return clean_html
