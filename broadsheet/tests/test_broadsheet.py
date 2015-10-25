# coding: utf-8

import broadsheet


def test_pep_396_version():
    assert isinstance(broadsheet.__version__, basestring)
