from setuptools import setup, find_packages

setup(
    name='karrot-backend',
    version='0.1',
    description='Karrot',
    url='http://github.com/yunity/karrot-backend',
    author='Karrot Team',
    author_email='info@karrot.world',
    license='AGPL',
    packages=find_packages(
        include=['config', 'karrot', 'karrot.*'],
        exclude=['config/local_settings'],  # doesn't work :(
    ),
    package_data={
        'config': ['options.env'],
        'karrot': ['*/templates/*.jinja2', 'COMMIT'],
    },
    include_package_data=True,
    zip_safe=False
)
