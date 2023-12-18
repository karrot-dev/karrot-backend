from io import BytesIO
from typing import Tuple

from django.core.files import File
from PIL import Image
from PIL.ImageOps import exif_transpose

# A list of mime types that pillow supports
Image.init()
PILLOW_SUPPORTED_MIME_TYPES = {Image.MIME[id] for id in Image.ID if id in Image.MIME}


def is_supported_content_type(content_type: str) -> bool:
    if not content_type:
        return False

    return content_type.lower() in PILLOW_SUPPORTED_MIME_TYPES


def resize_image(image: Image, size: Tuple[int, int]) -> File:
    # processes rotation if present
    image = exif_transpose(image)
    # remove alpha if it has it
    if image.mode in ["RGBA", "P"]:
        image = image.convert("RGB")
    image.thumbnail(size)
    io = BytesIO()
    image.save(
        io,
        format="JPEG",
        optimize=True,
        progressive=True,
    )
    return File(io)
