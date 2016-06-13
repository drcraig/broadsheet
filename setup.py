# coding: utf-8

import os.path
from setuptools import setup, find_packages

__version__ = ''
with open(os.path.join(os.path.dirname(__file__), 'broadsheet', 'version.py')) as version_file:
    exec(version_file.read())

setup(
    name='broadsheet',
    description='A single user, self-hosted RSS reader',
    url='https://github.com/drcraig/broadsheet',
    author='Dan Craig',
    author_email='drcraig@gmail.com',
    version=__version__,
    packages=find_packages(),
    install_requires=[
        "flask",
        "Flask-Script",
        "feedparser",
        "eventlet",
        "dateparser",
        "pyOpenSSL",
        "ndg-httpsclient",
        "pyasn1",
    ]
)
