from setuptools import find_packages, setup

setup(
    name="karrot-backend",
    version="0.1",
    description="Karrot",
    url="https://codeberg.org/karrot/karrot-backend",
    author="Karrot Team",
    author_email="info@karrot.world",
    license="AGPL",
    packages=find_packages(
        include=["config", "karrot", "karrot.*"],
    ),
    package_data={
        "config": ["options.env"],
        "karrot": ["*/templates/*.jinja2", "COMMIT"],
    },
    include_package_data=True,
    exclude_package_data={"config": ["local_settings"]},
    zip_safe=False,
)
