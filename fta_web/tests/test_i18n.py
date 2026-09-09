"""
Server-side error localization (fta_web/i18n.py plus the app.py error handler).

The contract is narrow on purpose (see i18n.py's docstring): only the
context-free capability/permission messages are translated, ``code`` and
``detail`` are never touched, and anything not in the catalog falls through to
English. These tests pin exactly that.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fta_web import i18n  # noqa: E402


# --------------------------------------------------------------------------
# language resolution
# --------------------------------------------------------------------------


class TestResolveLanguage:
    @pytest.mark.parametrize(
        "lang_param,accept,expected",
        [
            ("ja", None, "ja"),
            ("JA", None, "ja"),
            ("ja-JP", None, "ja"),
            ("en", None, "en"),
            (None, "ja,en;q=0.9", "ja"),
            (None, "en-US,en;q=0.9", "en"),
            (None, "de,ja;q=0.5", "ja"),
            (None, "de-DE", "en"),
            ("fr", None, "en"),
            (None, None, "en"),
            (None, "", "en"),
        ],
    )
    def test_selection(self, lang_param, accept, expected):
        assert i18n.resolve_language(lang_param, accept) == expected

    def test_lang_param_beats_accept_language(self):
        assert i18n.resolve_language("ja", "en-US,en;q=0.9") == "ja"
        assert i18n.resolve_language("en", "ja") == "en"

    def test_a_malformed_accept_language_does_not_raise(self):
        # This runs in an error path; it must degrade, not add a failure.
        assert i18n.resolve_language(None, "ja;q=notanumber, , ;;") in {"ja", "en"}


# --------------------------------------------------------------------------
# message localization
# --------------------------------------------------------------------------


class TestLocalizeError:
    def _err(self, code="AI_NOT_CONFIGURED", message="English text", detail=None):
        e = {"code": code, "message": message}
        if detail is not None:
            e["detail"] = detail
        return {"ok": False, "error": e}

    def test_japanese_swaps_a_known_code(self):
        out = i18n.localize_error(self._err(), "ja")
        assert out["error"]["message"] != "English text"
        assert "AI" in out["error"]["message"]  # the JA string still names it

    def test_english_is_a_no_op(self):
        payload = self._err()
        assert i18n.localize_error(payload, "en") == payload

    def test_an_unknown_code_falls_through_to_english(self):
        out = i18n.localize_error(self._err(code="SOMETHING_NEW"), "ja")
        assert out["error"]["message"] == "English text"

    def test_code_and_detail_are_never_touched(self):
        out = i18n.localize_error(
            self._err(detail={"path": "/etc/passwd", "reason": "outside_root"}), "ja"
        )
        assert out["error"]["code"] == "AI_NOT_CONFIGURED"
        assert out["error"]["detail"] == {"path": "/etc/passwd", "reason": "outside_root"}

    def test_the_input_payload_is_not_mutated(self):
        payload = self._err()
        i18n.localize_error(payload, "ja")
        assert payload["error"]["message"] == "English text"

    def test_a_body_without_an_error_object_is_returned_unchanged(self):
        ok_body = {"ok": True, "tree": {}}
        assert i18n.localize_error(ok_body, "ja") is ok_body

    @pytest.mark.parametrize(
        "code",
        [
            "AI_NOT_CONFIGURED",
            "RENDERER_UNAVAILABLE",
            "EXPORT_UNAVAILABLE",
            "PATH_REJECTED",
            "NO_CURRENT_PATH",
            "UNSAVED_CHANGES",
            "ROOT_PROTECTED",
            "CYCLE_REJECTED",
            "FORBIDDEN",
        ],
    )
    def test_every_catalogued_code_has_a_non_empty_japanese_string(self, code):
        out = i18n.localize_error(self._err(code=code, message="EN"), "ja")
        msg = out["error"]["message"]
        assert msg and msg != "EN"
        # crude "is this actually Japanese" check: at least one CJK/kana char
        assert any(ord(c) > 0x3000 for c in msg), msg


# --------------------------------------------------------------------------
# end to end through the Flask handler
# --------------------------------------------------------------------------


class TestThroughTheApp:
    @pytest.fixture
    def client(self):
        flask = pytest.importorskip("flask")
        from fta_web.app import create_app
        from fta_web.state import reset_state

        reset_state()
        app = create_app()
        app.config.update(TESTING=True)
        with app.test_client() as c:
            yield c

    def test_a_404_is_english_by_default(self, client):
        body = client.get("/api/does-not-exist").get_json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert not any(ord(c) > 0x3000 for c in body["error"]["message"])

    def test_a_404_is_japanese_with_lang_ja(self, client):
        body = client.get("/api/does-not-exist?lang=ja").get_json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert any(ord(c) > 0x3000 for c in body["error"]["message"])

    def test_a_404_is_japanese_via_accept_language(self, client):
        body = client.get(
            "/api/does-not-exist", headers={"Accept-Language": "ja,en;q=0.8"}
        ).get_json()
        assert any(ord(c) > 0x3000 for c in body["error"]["message"])

    def test_the_code_is_stable_across_languages(self, client):
        en = client.get("/api/x").get_json()["error"]["code"]
        ja = client.get("/api/x?lang=ja").get_json()["error"]["code"]
        assert en == ja == "NOT_FOUND"
