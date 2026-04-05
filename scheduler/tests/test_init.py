# -*- coding: utf-8 -*-
"""Verify scheduler package can be imported."""


def test_import_scheduler():
    import scheduler
    assert scheduler is not None
