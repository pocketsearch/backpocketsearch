"""Unit tests for the Groq-backed assistant module and Flask route."""

import importlib
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_assistant(env: dict):
    """Reload the assistant module with the supplied environment variables."""
    with patch.dict(os.environ, env, clear=False):
        import assistant
        importlib.reload(assistant)
        return assistant


# ---------------------------------------------------------------------------
# assistant.py – configuration and get_response()
# ---------------------------------------------------------------------------

class TestIsEnabled(unittest.TestCase):
    def test_disabled_when_key_missing(self):
        env = {k: v for k, v in os.environ.items() if k != "GROQ_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            import assistant
            importlib.reload(assistant)
            self.assertFalse(assistant.is_enabled())

    def test_disabled_when_key_blank(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "   "}, clear=False):
            import assistant
            importlib.reload(assistant)
            self.assertFalse(assistant.is_enabled())

    def test_enabled_when_key_set(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key-123"}, clear=False):
            import assistant
            importlib.reload(assistant)
            self.assertTrue(assistant.is_enabled())


class TestGetResponse(unittest.TestCase):
    def _make_mock_groq(self, content: str):
        """Build a minimal mock that looks like the groq.Groq client."""
        message = MagicMock()
        message.content = content
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        client = MagicMock()
        client.chat.completions.create.return_value = completion
        groq_module = types.ModuleType("groq")
        groq_module.Groq = MagicMock(return_value=client)
        return groq_module, client

    def test_raises_when_disabled(self):
        env = {k: v for k, v in os.environ.items() if k != "GROQ_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            import assistant
            importlib.reload(assistant)
            with self.assertRaises(assistant.AssistantDisabledError):
                assistant.get_response("hello")

    def test_returns_model_content(self):
        groq_module, mock_client = self._make_mock_groq("42")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False):
            with patch.dict(sys.modules, {"groq": groq_module}):
                import assistant
                importlib.reload(assistant)
                result = assistant.get_response("What is 6 * 7?")
        self.assertEqual(result, "42")

    def test_uses_custom_model_env(self):
        groq_module, mock_client = self._make_mock_groq("ok")
        custom_model = "mixtral-8x7b-32768"
        env = {"GROQ_API_KEY": "test-key", "GROQ_MODEL": custom_model}
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(sys.modules, {"groq": groq_module}):
                import assistant
                importlib.reload(assistant)
                assistant.get_response("hi")
        self.assertEqual(
            mock_client.chat.completions.create.call_args.kwargs.get("model"),
            custom_model,
        )

    def test_system_prompt_included(self):
        groq_module, mock_client = self._make_mock_groq("sure")
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False):
            with patch.dict(sys.modules, {"groq": groq_module}):
                import assistant
                importlib.reload(assistant)
                assistant.get_response("test question")
        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("concise", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "test question")

    def test_custom_timeout_env(self):
        groq_module, _ = self._make_mock_groq("ok")
        env = {"GROQ_API_KEY": "test-key", "GROQ_TIMEOUT": "15"}
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(sys.modules, {"groq": groq_module}):
                import assistant
                importlib.reload(assistant)
                assistant.get_response("hi")
        groq_module.Groq.assert_called_once_with(api_key="test-key", timeout=15)

    def test_invalid_timeout_falls_back_to_default(self):
        groq_module, _ = self._make_mock_groq("ok")
        env = {"GROQ_API_KEY": "test-key", "GROQ_TIMEOUT": "not-a-number"}
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(sys.modules, {"groq": groq_module}):
                import assistant
                importlib.reload(assistant)
                assistant.get_response("hi")
        import assistant as _a
        groq_module.Groq.assert_called_once_with(api_key="test-key", timeout=_a._DEFAULT_TIMEOUT)


# ---------------------------------------------------------------------------
# Flask route – /assistant
# ---------------------------------------------------------------------------

class TestAssistantRoute(unittest.TestCase):
    def setUp(self):
        # Ensure SECRET_KEY is set so app.py can be imported
        os.environ.setdefault("SECRET_KEY", "test-secret-key-for-tests")
        # Provide minimal mocks for heavy optional deps before importing app
        for mod in ("knowledge", "recon", "ipstack", "pass_search"):
            if mod not in sys.modules:
                sys.modules[mod] = MagicMock()
        import app as flask_app
        flask_app.app.config["TESTING"] = True
        self.client = flask_app.app.test_client()
        self.flask_app = flask_app

    def _render_patch(self, template, **ctx):
        """Stub render_template that returns a plain-text response."""
        import flask
        parts = [template]
        for k, v in ctx.items():
            parts.append(f"{k}={v!r}")
        return flask.Response("\n".join(parts), content_type="text/plain")

    def test_get_assistant_disabled(self):
        """GET /assistant without GROQ_API_KEY shows disabled=True in context."""
        env = {k: v for k, v in os.environ.items() if k != "GROQ_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            import assistant
            importlib.reload(assistant)
            self.flask_app.assistantlib = assistant
            with patch("app.render_template", side_effect=self._render_patch):
                resp = self.client.get("/assistant")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"enabled=False", resp.data)

    def test_post_returns_answer(self):
        """POST /assistant with a valid key passes answer to template."""
        groq_module, _ = self._make_mock_groq("Paris")
        env = {"GROQ_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(sys.modules, {"groq": groq_module}):
                import assistant
                importlib.reload(assistant)
                self.flask_app.assistantlib = assistant
                with patch("app.render_template", side_effect=self._render_patch):
                    resp = self.client.post("/assistant", data={"query": "Capital of France?"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Paris", resp.data)

    def test_post_empty_query_shows_error(self):
        env = {"GROQ_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=False):
            import assistant
            importlib.reload(assistant)
            self.flask_app.assistantlib = assistant
            with patch("app.render_template", side_effect=self._render_patch):
                resp = self.client.post("/assistant", data={"query": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Please enter a question", resp.data)

    def test_post_api_error_shows_generic_error(self):
        """A groq API exception is caught and a friendly message shown."""
        groq_module = types.ModuleType("groq")
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API down")
        groq_module.Groq = MagicMock(return_value=mock_client)
        env = {"GROQ_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=False):
            with patch.dict(sys.modules, {"groq": groq_module}):
                import assistant
                importlib.reload(assistant)
                self.flask_app.assistantlib = assistant
                with patch("app.render_template", side_effect=self._render_patch):
                    resp = self.client.post("/assistant", data={"query": "anything"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"failed", resp.data)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_mock_groq(self, content: str):
        message = MagicMock()
        message.content = content
        choice = MagicMock()
        choice.message = message
        completion = MagicMock()
        completion.choices = [choice]
        client = MagicMock()
        client.chat.completions.create.return_value = completion
        groq_module = types.ModuleType("groq")
        groq_module.Groq = MagicMock(return_value=client)
        return groq_module, client


if __name__ == "__main__":
    unittest.main()
