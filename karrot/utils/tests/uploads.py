import json
import os
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile

image_path = os.path.join(os.path.dirname(__file__), './photo.jpg')
pdf_attachment_path = os.path.join(os.path.dirname(__file__), './dummy.pdf')


def encode_data_with_images(data):
    post_data = {}
    for index, image in enumerate(data.get('images', [])):
        image_file = image.pop('image', None)
        if image_file:
            post_data['images.{}.image'.format(index)] = image_file
    data_file = StringIO(json.dumps(data))
    setattr(data_file, 'content_type', 'application/json')
    post_data['document'] = data_file
    return post_data


def encode_data_with_attachments(data):
    post_data = {}
    for index, attachment in enumerate(data.get('attachments', [])):
        attachment_file = attachment.pop('file', None)
        if attachment_file:
            post_data['attachments.{}.file'.format(index)] = attachment_file
    data_file = StringIO(json.dumps(data))
    setattr(data_file, 'content_type', 'application/json')
    post_data['document'] = data_file
    return post_data


def uploaded_file_for(path):
    """Gives you something you can pass into an models image field from a path to a file"""
    with open(path, 'rb') as file:
        return SimpleUploadedFile(
            name=os.path.basename(path),
            content=file.read(),
            content_type='image/jpeg',
        )


def read_response(response) -> bytes:
    if not response.streaming:
        raise AssertionError('must be a streaming response')
    data = b''
    for chunk in response:
        data += chunk
    return data
