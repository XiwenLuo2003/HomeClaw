from __future__ import annotations

import unittest
import urllib.error
from unittest.mock import patch

from homeclaw.config import LLMConfig
from homeclaw.llm import AnthropicClient, OpenAICompatibleClient


class LLMClientTransportTests(unittest.TestCase):
    @staticmethod
    def _config() -> LLMConfig:
        return LLMConfig(
            provider="openai",
            model="test-model",
            api_key="test-key",
            base_url="https://provider.invalid/v1",
            timeout_seconds=1,
        )

    def test_openai_rate_limit_is_classified_as_transient(self) -> None:
        error = urllib.error.HTTPError(
            "https://provider.invalid/v1/chat/completions",
            429,
            "rate limited",
            None,
            None,
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ConnectionError):
                OpenAICompatibleClient(self._config()).chat(
                    [{"role": "user", "content": "hello"}]
                )

    def test_openai_bad_request_is_not_classified_as_transient(self) -> None:
        error = urllib.error.HTTPError(
            "https://provider.invalid/v1/chat/completions",
            400,
            "bad request",
            None,
            None,
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ValueError):
                OpenAICompatibleClient(self._config()).chat(
                    [{"role": "user", "content": "hello"}]
                )

    def test_anthropic_transport_failure_is_classified_as_transient(self) -> None:
        error = urllib.error.URLError("connection refused")
        config = self._config()
        config.provider = "anthropic"
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(ConnectionError):
                AnthropicClient(config).chat([{"role": "user", "content": "hello"}])


if __name__ == "__main__":
    unittest.main()
