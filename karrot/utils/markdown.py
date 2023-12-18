import bleach
import markdown
from bleach_allowlist import markdown_attrs, markdown_tags
from django.utils.text import Truncator
from markdown import Extension
from markdown.extensions.nl2br import Nl2BrExtension
from markdown.postprocessors import Postprocessor
from pymdownx.emoji import EmojiExtension, twemoji
from pymdownx.magiclink import MagiclinkExtension
from pymdownx.superfences import SuperFencesCodeExtension
from pymdownx.tilde import DeleteSubExtension


class MentionsPostProcessor(Postprocessor):
    def __init__(self, mentions):
        super().__init__()
        self.mentions = mentions

    def run(self, text):
        for mention in self.mentions:
            mention_text = f"@{mention.user.username}"
            text = text.replace(
                mention_text,
                f"<strong>{mention_text}</strong>",
            )
        return text


class MentionsExtension(Extension):
    def __init__(self, mentions):
        super().__init__()
        self.mentions = mentions

    def extendMarkdown(self, md):
        processor = MentionsPostProcessor(self.mentions)
        md.postprocessors.register(processor, "mentions", 150)


def render(text, truncate_words=None, mentions=None):
    extensions = [
        EmojiExtension(emoji_index=twemoji),
        SuperFencesCodeExtension(),
        MagiclinkExtension(),
        DeleteSubExtension(subscript=False),
        Nl2BrExtension(),
    ]

    if mentions:
        extensions.append(MentionsExtension(mentions))

    html = markdown.markdown(text, extensions=extensions)
    markdown_attrs["img"].append("class")
    markdown_tags.append("pre")
    clean_html = bleach.clean(html, markdown_tags, markdown_attrs)

    if truncate_words:
        clean_html = Truncator(clean_html).words(num=truncate_words, html=True)

    return clean_html
