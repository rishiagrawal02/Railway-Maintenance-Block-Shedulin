"""One compact UI flow across the six supported screens."""

from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from rbp import api

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_ui_run_cache_and_six_pages():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    assert not app.exception
    pages = app.sidebar.radio(key="page")
    assert len(pages.options) == 6
    assert "Algorithm Laboratory" not in pages.options
    assert "Experiment History" not in pages.options
    app.sidebar.number_input[0].set_value(6)
    next(b for b in app.sidebar.button if b.label == "Generate instance").click().run()
    with patch("rbp.api.run", wraps=api.run) as run:
        next(b for b in app.sidebar.button if b.label == "Run").click().run()
        assert not app.exception
        assert app.session_state["result"]["metrics"]["violations"] == 0
        objective = app.session_state["result"]["metrics"]["objective"]
        next(b for b in app.sidebar.button if b.label == "Run").click().run()
        assert run.call_count == 1
        assert app.session_state["result"]["metrics"]["objective"] == objective
    for page in pages.options:
        app.sidebar.radio(key="page").set_value(page).run()
        assert not app.exception, page
        if page == "Performance Analytics":
            next(b for b in app.button if b.label == "Compare algorithms").click().run()
            assert not app.exception
            assert len(app.session_state["comparison"]) == 2
    app.sidebar.selectbox[-1].select("WIS-DP").run()
    assert next(b for b in app.sidebar.button if b.label == "Run").disabled
    assert any("Not applicable" in w.value for w in app.warning)


def test_upload_errors_are_messages():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.sidebar.radio[1].set_value("Upload JSON")
    invalid = api.generate_instance(n=3)
    invalid["tasks"][0]["duration"] = -1
    for content, message in [
        (b'{"tasks":', "Malformed JSON"),
        (api.to_json(invalid).encode(), "E_DURATION"),
    ]:
        with patch("streamlit.file_uploader", return_value=BytesIO(content)):
            app.run()
        assert not app.exception
        assert any(message in error.value for error in app.error)
        assert next(b for b in app.sidebar.button if b.label == "Run").disabled
