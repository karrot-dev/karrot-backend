from setuptools import setup, find_packages

setup(
    name='karrot',
    version='0.1',
    description='Karrot',
    url='http://github.com/yunity/karrot-backend',
    author='Karrot Team',
    author_email='info@karrot.world',
    license='MIT',
    packages=find_packages(include=['config', 'karrot', 'karrot.*']),
    zip_safe=False
)
