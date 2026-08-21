from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from virinda.domain.models import Message, ProviderRequest
from virinda.infrastructure.providers.ask_adapter import AskCompletionProvider


class MockAskBackend:
    def __init__(self, token_chunks: list[str] | None = None, raise_error: bool = False):
        self.token_chunks = token_chunks if token_chunks is not None else ["Hello", " world", "!"]
        self.raise_error = raise_error
        self.last_query = None

    def send_query(
        self,
        prompt: str,
        system_prompt: str | None = None,
        stream: bool = True,
        model: str | None = None,
    ):
        self.last_query = {
            "prompt": prompt,
            "system_prompt": system_prompt,
            "stream": stream,
            "model": model,
        }
        if self.raise_error:
            from ask.providers import ProviderEvent

            yield ProviderEvent(type="error", data="Simulated network failure")
            return

        from ask.providers import ProviderEvent

        for token in self.token_chunks:
            yield ProviderEvent(type="token", data=token)
        yield ProviderEvent(type="complete", data="".join(self.token_chunks))


class TestAskCompletionProvider(unittest.TestCase):
    def test_extract_prompts_with_system_and_multiturn(self):
        provider = AskCompletionProvider(name="ask")
        req = ProviderRequest(
            generation_id=1,
            model="meta/llama-3.3-70b-instruct",
            messages=(
                Message(role="system", content="You are a helpful ambient assistant."),
                Message(role="user", content="What time is it?"),
                Message(role="assistant", content="It is 6:00 PM."),
                Message(role="user", content="Set a timer for 10 minutes."),
            ),
        )

        system_prompt, prompt = provider._extract_prompts(req)
        self.assertEqual(system_prompt, "You are a helpful ambient assistant.")
        expected_prompt = (
            "User: What time is it?\nAssistant: It is 6:00 PM.\nUser: Set a timer for 10 minutes."
        )
        self.assertEqual(prompt, expected_prompt)

    def test_extract_prompts_single_user_message(self):
        provider = AskCompletionProvider(name="ask")
        req = ProviderRequest(
            generation_id=2,
            model="meta/llama-3.3-70b-instruct",
            messages=(Message(role="user", content="Hello Marina!"),),
        )

        system_prompt, prompt = provider._extract_prompts(req)
        self.assertIsNone(system_prompt)
        self.assertEqual(prompt, "Hello Marina!")

    def test_extract_prompts_with_custom_and_empty_roles(self):
        provider = AskCompletionProvider(name="ask")
        req = ProviderRequest(
            generation_id=3,
            model="meta/llama-3.3-70b-instruct",
            messages=(
                Message(role="system", content=""),  # empty content ignored
                Message(role="tool", content="Tool result: ok"),
                Message(role="user", content="Next step"),
            ),
        )

        system_prompt, prompt = provider._extract_prompts(req)
        self.assertIsNone(system_prompt)
        self.assertEqual(prompt, "Tool: Tool result: ok\nUser: Next step")

    def test_streaming_tokens_mock_backend(self):
        provider = AskCompletionProvider(
            name="ask", ask_provider="mock", default_model="mock-echo-v1"
        )
        req = ProviderRequest(
            generation_id=4,
            model="mock-echo-v1",
            messages=(Message(role="user", content="Echo test"),),
        )

        mock_backend = MockAskBackend(["Part1", " ", "Part2"])
        with patch(
            "virinda.infrastructure.providers.ask_adapter.get_provider", return_value=mock_backend
        ):
            tokens = list(provider.stream(req))

        self.assertEqual(tokens, ["Part1", " ", "Part2"])
        self.assertEqual(mock_backend.last_query["prompt"], "Echo test")
        self.assertIsNone(mock_backend.last_query["system_prompt"])

    def test_streaming_error_raises_runtime_error(self):
        provider = AskCompletionProvider(name="ask", ask_provider="nim")
        req = ProviderRequest(
            generation_id=5,
            model="meta/llama-3.3-70b-instruct",
            messages=(Message(role="user", content="Trigger error"),),
        )

        mock_backend = MockAskBackend(raise_error=True)
        with patch(
            "virinda.infrastructure.providers.ask_adapter.get_provider", return_value=mock_backend
        ):
            with self.assertRaises(RuntimeError) as ctx:
                list(provider.stream(req))

        self.assertIn("Simulated network failure", str(ctx.exception))

    def test_generator_cancellation_exits_cleanly(self):
        provider = AskCompletionProvider(name="ask")
        req = ProviderRequest(
            generation_id=6,
            model="meta/llama-3.3-70b-instruct",
            messages=(Message(role="user", content="Long stream"),),
        )

        mock_backend = MockAskBackend(["1", "2", "3", "4", "5"])
        with patch(
            "virinda.infrastructure.providers.ask_adapter.get_provider", return_value=mock_backend
        ):
            stream_iter = provider.stream(req)
            first_token = next(stream_iter)
            self.assertEqual(first_token, "1")
            stream_iter.close()  # Simulate barge-in cancellation

    def test_metadata_provider_override(self):
        provider = AskCompletionProvider(name="ask", ask_provider="default_backend")
        req = ProviderRequest(
            generation_id=7,
            model="meta/llama-3.3-70b-instruct",
            messages=(Message(role="user", content="Override check"),),
            metadata={"provider": "nim"},
        )

        mock_backend = MockAskBackend(["ok"])
        with patch(
            "virinda.infrastructure.providers.ask_adapter.get_provider", return_value=mock_backend
        ) as mock_get:
            tokens = list(provider.stream(req))
            self.assertEqual(tokens, ["ok"])
            mock_get.assert_called_once_with(
                provider_name="nim",
                model="meta/llama-3.3-70b-instruct",
                api_key=None,
                headless=True,
            )

    def test_concurrent_streams_isolated(self):
        provider = AskCompletionProvider(name="ask")

        def run_stream(worker_id: int) -> str:
            req = ProviderRequest(
                generation_id=worker_id,
                model=f"model-{worker_id}",
                messages=(Message(role="user", content=f"Hello from {worker_id}"),),
            )
            backend = MockAskBackend([f"w{worker_id}-token1", f"w{worker_id}-token2"])
            with patch(
                "virinda.infrastructure.providers.ask_adapter.get_provider", return_value=backend
            ):
                return "".join(provider.stream(req))

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(run_stream, range(10)))

        for i, res in enumerate(results):
            self.assertEqual(res, f"w{i}-token1w{i}-token2")


if __name__ == "__main__":
    unittest.main()
