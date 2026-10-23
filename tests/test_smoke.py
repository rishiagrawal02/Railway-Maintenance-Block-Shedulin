"""Smoke tests for rbp package."""


def test_import_rbp():
    import rbp
    import rbp.api

    assert rbp.__version__ == "0.1.0"
    assert rbp.api.get_version() == "0.1.0"
