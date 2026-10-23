"""Tests verifying marker behavior for pytest."""

import pytest


@pytest.mark.slow
def test_slow_marker_behavior():
    """This test is marked slow and should be deselected by default with 'not slow'."""
    assert True
