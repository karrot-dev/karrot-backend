import json
import os
from io import StringIO

from django.core.files.uploadedfile import SimpleUploadedFile

image_path = os.path.join(os.path.dirname(__file__), './photo.jpg')
pdf_file_path = os.path.join(os.path.dirname(__file__), './dummy.pdf')


def encode_upload_data(data):
    post_data = {}

    if 'images' in data:
        for index, image in enumerate(data.get('images', [])):
            image_file = image.pop('image', None)
            if image_file:
                post_data['images.{}.image'.format(index)] = image_file

    if 'attachments' in data:
        for index, attachment in enumerate(data.get('attachments', [])):
            image_file = attachment.pop('image', None)
            if image_file:
                post_data['attachments.{}.image'.format(index)] = image_file

            attachment_file = attachment.pop('file', None)
            if attachment_file:
                post_data['attachments.{}.file'.format(index)] = attachment_file

    data_file = StringIO(json.dumps(data))
    setattr(data_file, 'content_type', 'application/json')
    post_data['document'] = data_file
    return post_data


def uploaded_file_for(path, content_type='image/jpeg'):
    """Gives you something you can pass into an models image field from a path to a file"""
    with open(path, 'rb') as file:
        return SimpleUploadedFile(
            name=os.path.basename(path),
            content=file.read(),
            content_type=content_type,
        )
