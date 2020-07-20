import json
import os
from io import StringIO

image_path = os.path.join(os.path.dirname(__file__), './photo.jpg')


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
