"""
Tests for utils.py — parse_uploaded_file and analyze_fit.

Run with:
    pip install pytest
    pytest tests/
"""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

import anthropic as anthropic_lib


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_file(name: str, content: bytes = b"") -> MagicMock:
    f = MagicMock()
    f.name = name
    f.read.return_value = content
    return f


def _mock_claude_response(text: str) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


VALID_PAYLOAD = {
    "fit_score": 72,
    "sub_scores": {
        "skills": 75,
        "experience": 80,
        "domain": 65,
        "education": 60,
    },
    "score_rationale": "Strong skills and experience offset by a weaker domain match.",
    "strengths": ["5 years Python experience", "People analytics background"],
    "gaps": ["No SQL certification listed"],
    "quick_wins": ["Add SQL projects to CV"],
    "recruiter_summary": "Strong analytical profile with one minor gap.",
}

VALID_TAILOR_PAYLOAD = {
    "summary": "Reworded two bullets to surface Python and SQL keywords from the JD.",
    "tailored_bullets": [
        {
            "original": "Built internal reporting tools for the analytics team.",
            "rewritten": "Built internal reporting tools in Python and SQL for the analytics team.",
            "reason": "Surfaces Python/SQL, both required by the JD.",
        },
    ],
}


# ── parse_uploaded_file ───────────────────────────────────────────────────────

class TestParseUploadedFile:

    def setup_method(self):
        from utils import parse_uploaded_file
        self.parse = parse_uploaded_file

    def test_txt_utf8(self):
        f = _mock_file("cv.txt", b"Hello world")
        text, err = self.parse(f)
        assert text == "Hello world"
        assert err == ""

    def test_txt_non_utf8_does_not_crash(self):
        # Latin-1 byte 0xe9 ('é') is invalid UTF-8 — should use replacement char
        f = _mock_file("cv.txt", b"caf\xe9")
        text, err = self.parse(f)
        assert err == ""
        assert "caf" in text  # content preserved up to the bad byte

    def test_pdf_success(self):
        f = _mock_file("cv.pdf")
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page one text"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader
        with patch.dict(sys.modules, {"pypdf": mock_pypdf}):
            text, err = self.parse(f)
        assert text == "Page one text"
        assert err == ""

    def test_pdf_multiple_pages_joined(self):
        f = _mock_file("cv.pdf")
        pages = [MagicMock(), MagicMock()]
        pages[0].extract_text.return_value = "Page 1"
        pages[1].extract_text.return_value = "Page 2"
        mock_reader = MagicMock()
        mock_reader.pages = pages
        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader
        with patch.dict(sys.modules, {"pypdf": mock_pypdf}):
            text, err = self.parse(f)
        assert "Page 1" in text
        assert "Page 2" in text

    def test_pdf_page_returns_none_handled(self):
        # extract_text() can return None for image-only pages
        f = _mock_file("cv.pdf")
        mock_page = MagicMock()
        mock_page.extract_text.return_value = None
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.return_value = mock_reader
        with patch.dict(sys.modules, {"pypdf": mock_pypdf}):
            text, err = self.parse(f)
        assert err == ""  # should not crash

    def test_pdf_read_error(self):
        f = _mock_file("cv.pdf")
        mock_pypdf = MagicMock()
        mock_pypdf.PdfReader.side_effect = Exception("corrupted PDF")
        with patch.dict(sys.modules, {"pypdf": mock_pypdf}):
            text, err = self.parse(f)
        assert text == ""
        assert "corrupted PDF" in err

    def test_docx_success(self):
        f = _mock_file("cv.docx")
        mock_para = MagicMock()
        mock_para.text = "Work experience paragraph"
        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]
        mock_docx = MagicMock()
        mock_docx.Document.return_value = mock_doc
        with patch.dict(sys.modules, {"docx": mock_docx}):
            text, err = self.parse(f)
        assert text == "Work experience paragraph"
        assert err == ""

    def test_doc_extension_also_handled(self):
        f = _mock_file("cv.doc")
        mock_doc = MagicMock()
        mock_doc.paragraphs = []
        mock_docx = MagicMock()
        mock_docx.Document.return_value = mock_doc
        with patch.dict(sys.modules, {"docx": mock_docx}):
            text, err = self.parse(f)
        assert err == ""

    def test_docx_read_error(self):
        f = _mock_file("cv.docx")
        mock_docx = MagicMock()
        mock_docx.Document.side_effect = Exception("bad file")
        with patch.dict(sys.modules, {"docx": mock_docx}):
            text, err = self.parse(f)
        assert text == ""
        assert "bad file" in err

    def test_unsupported_type_returns_error(self):
        f = _mock_file("cv.csv")
        text, err = self.parse(f)
        assert text == ""
        assert "Unsupported" in err
        assert "cv.csv" in err

    def test_unsupported_type_png(self):
        f = _mock_file("photo.png")
        text, err = self.parse(f)
        assert text == ""
        assert "photo.png" in err


# ── analyze_fit ───────────────────────────────────────────────────────────────

class TestAnalyzeFit:

    @pytest.fixture(autouse=True)
    def _reset_client_cache(self):
        # The module caches the Anthropic client after first construction.
        # Reset it before each test so patches on utils.anthropic.Anthropic
        # take effect and tests stay independent.
        import utils
        utils._client = None
        yield
        utils._client = None

    def _call(self, cv="my cv text", jd="job description text"):
        from utils import analyze_fit
        return analyze_fit(cv, jd)

    def test_missing_api_key_raises_runtime_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("utils._get_secret", return_value=""):
                with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                    self._call()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_valid_response_returns_all_fields(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(json.dumps(VALID_PAYLOAD))
            )
            result = self._call()

        assert result["fit_score"] == 72
        assert result["strengths"] == VALID_PAYLOAD["strengths"]
        assert result["gaps"] == VALID_PAYLOAD["gaps"]
        assert result["quick_wins"] == VALID_PAYLOAD["quick_wins"]
        assert result["recruiter_summary"] == VALID_PAYLOAD["recruiter_summary"]
        assert "full_response" in result

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_json_backtick_fences_stripped(self):
        fenced = f"```json\n{json.dumps(VALID_PAYLOAD)}\n```"
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(fenced)
            )
            result = self._call()
        assert result["fit_score"] == 72

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_bare_fences_stripped(self):
        fenced = f"```\n{json.dumps(VALID_PAYLOAD)}\n```"
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(fenced)
            )
            result = self._call()
        assert result["fit_score"] == 72

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_invalid_json_raises_value_error(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response("Sorry, I cannot analyse this.")
            )
            with pytest.raises(ValueError, match="JSON"):
                self._call()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_api_error_raises_runtime_error(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = (
                anthropic_lib.APIConnectionError(request=MagicMock())
            )
            with pytest.raises(RuntimeError, match="API error"):
                self._call()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_fit_score_boundary_zero(self):
        payload = {
            **VALID_PAYLOAD,
            "sub_scores": {"skills": 0, "experience": 0, "domain": 0, "education": 0},
        }
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(json.dumps(payload))
            )
            result = self._call()
        assert result["fit_score"] == 0

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_fit_score_boundary_hundred(self):
        payload = {
            **VALID_PAYLOAD,
            "sub_scores": {"skills": 100, "experience": 100, "domain": 100, "education": 100},
        }
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(json.dumps(payload))
            )
            result = self._call()
        assert result["fit_score"] == 100

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_fit_score_is_derived_from_sub_scores(self):
        # Model emits a bogus fit_score; analyze_fit must overwrite it with
        # the weighted rollup of sub_scores.
        payload = {
            **VALID_PAYLOAD,
            "fit_score": 99,
            "sub_scores": {"skills": 80, "experience": 70, "domain": 60, "education": 50},
        }
        expected = round(0.35 * 80 + 0.30 * 70 + 0.25 * 60 + 0.10 * 50)
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(json.dumps(payload))
            )
            result = self._call()
        assert result["fit_score"] == expected
        assert result["fit_score"] != 99

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_prompt_caching_system_has_cache_control(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.messages.create.return_value = (
                _mock_claude_response(json.dumps(VALID_PAYLOAD))
            )
            self._call()

        kwargs = mock_instance.messages.create.call_args.kwargs
        assert isinstance(kwargs["system"], list)
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_prompt_caching_cv_block_has_cache_control(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.messages.create.return_value = (
                _mock_claude_response(json.dumps(VALID_PAYLOAD))
            )
            self._call(cv="my cv", jd="the jd")

        kwargs = mock_instance.messages.create.call_args.kwargs
        user_content = kwargs["messages"][0]["content"]
        # CV block (index 0) must be cached; JD block (index 1) must not be
        assert user_content[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in user_content[1]

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_cv_and_jd_text_passed_to_api(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.messages.create.return_value = (
                _mock_claude_response(json.dumps(VALID_PAYLOAD))
            )
            self._call(cv="UNIQUE_CV_MARKER", jd="UNIQUE_JD_MARKER")

        kwargs = mock_instance.messages.create.call_args.kwargs
        user_content = kwargs["messages"][0]["content"]
        assert "UNIQUE_CV_MARKER" in user_content[0]["text"]
        assert "UNIQUE_JD_MARKER" in user_content[1]["text"]


# ── tailor_cv ─────────────────────────────────────────────────────────────────

class TestTailorCv:

    @pytest.fixture(autouse=True)
    def _reset_client_cache(self):
        import utils
        utils._client = None
        yield
        utils._client = None

    def _call(self, cv="my cv text", jd="job description text"):
        from utils import tailor_cv
        return tailor_cv(cv, jd)

    def test_missing_api_key_raises_runtime_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("utils._get_secret", return_value=""):
                with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                    self._call()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_valid_response_returns_all_fields(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(json.dumps(VALID_TAILOR_PAYLOAD))
            )
            result = self._call()

        assert result["summary"] == VALID_TAILOR_PAYLOAD["summary"]
        assert result["tailored_bullets"] == VALID_TAILOR_PAYLOAD["tailored_bullets"]
        assert "full_response" in result

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_json_backtick_fences_stripped(self):
        fenced = f"```json\n{json.dumps(VALID_TAILOR_PAYLOAD)}\n```"
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(fenced)
            )
            result = self._call()
        assert result["summary"] == VALID_TAILOR_PAYLOAD["summary"]

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_bare_fences_stripped(self):
        fenced = f"```\n{json.dumps(VALID_TAILOR_PAYLOAD)}\n```"
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(fenced)
            )
            result = self._call()
        assert result["summary"] == VALID_TAILOR_PAYLOAD["summary"]

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_invalid_json_raises_value_error(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response("Sorry, I cannot tailor this.")
            )
            with pytest.raises(ValueError, match="JSON"):
                self._call()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_api_error_raises_runtime_error(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = (
                anthropic_lib.APIConnectionError(request=MagicMock())
            )
            with pytest.raises(RuntimeError, match="API error"):
                self._call()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_empty_bullets_list_is_valid(self):
        payload = {"summary": "No changes needed — the CV already matches the JD.", "tailored_bullets": []}
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = (
                _mock_claude_response(json.dumps(payload))
            )
            result = self._call()
        assert result["tailored_bullets"] == []

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_prompt_caching_system_has_cache_control(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.messages.create.return_value = (
                _mock_claude_response(json.dumps(VALID_TAILOR_PAYLOAD))
            )
            self._call()

        kwargs = mock_instance.messages.create.call_args.kwargs
        assert isinstance(kwargs["system"], list)
        assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_prompt_caching_cv_block_has_cache_control(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.messages.create.return_value = (
                _mock_claude_response(json.dumps(VALID_TAILOR_PAYLOAD))
            )
            self._call(cv="my cv", jd="the jd")

        kwargs = mock_instance.messages.create.call_args.kwargs
        user_content = kwargs["messages"][0]["content"]
        assert user_content[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in user_content[1]

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_cv_and_jd_text_passed_to_api(self):
        with patch("utils.anthropic.Anthropic") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.messages.create.return_value = (
                _mock_claude_response(json.dumps(VALID_TAILOR_PAYLOAD))
            )
            self._call(cv="UNIQUE_CV_MARKER", jd="UNIQUE_JD_MARKER")

        kwargs = mock_instance.messages.create.call_args.kwargs
        user_content = kwargs["messages"][0]["content"]
        assert "UNIQUE_CV_MARKER" in user_content[0]["text"]
        assert "UNIQUE_JD_MARKER" in user_content[1]["text"]

