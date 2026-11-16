"""Smoke tests for rbp package."""


def test_import_rbp():
    import rbp
    import rbp.api

    assert rbp.__version__ == "1.0.0"
    assert rbp.api.get_version() == "1.0.0"
