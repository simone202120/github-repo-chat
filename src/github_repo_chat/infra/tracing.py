"""Optional Langfuse tracing: LlamaIndex spans (retrieval, LLM, tokens) grouped per request."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from langfuse import Langfuse
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

from github_repo_chat.config import Settings

logger = logging.getLogger(__name__)

OutputSetter = Callable[[Any], None]


class Tracer:
    """Wraps a Langfuse client; every method is a no-op when tracing is disabled."""

    def __init__(self, client: Langfuse | None) -> None:
        self._client = client

    @contextmanager
    def trace(self, name: str, input_data: Any, metadata: dict[str, Any]) -> Iterator[OutputSetter]:
        """Opens a root span; LlamaIndex spans created inside it become its children."""
        if self._client is None:
            yield lambda _output: None
            return
        with self._client.start_as_current_observation(
            name=name, as_type="chain", input=input_data, metadata=metadata
        ) as span:

            def set_output(output: Any) -> None:
                span.update(output=output)

            yield set_output

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.shutdown()


def setup_tracing(settings: Settings) -> Tracer:
    if not settings.tracing_enabled:
        logger.info("Langfuse keys not set: tracing disabled")
        return Tracer(None)
    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        host=settings.langfuse_host,
    )
    LlamaIndexInstrumentor().instrument()
    logger.info("Langfuse tracing enabled (%s)", settings.langfuse_host)
    return Tracer(client)
