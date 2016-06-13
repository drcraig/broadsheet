# coding: utf-8

from flask import Flask

from .version import __version__  # pragma: no cover # noqa


app = Flask(__name__)


def index():
    return 'Hello world', 200
