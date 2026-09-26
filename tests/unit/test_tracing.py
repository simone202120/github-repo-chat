from contextlib import contextmanager

from github_repo_chat.config import Settings
from github_repo_chat.infra import tracing
from github_repo_chat.infra.tracing import Tracer, setup_tracing


class _FakeSpan:
    def __init__(self) -> None:
        self.outputs: list[object] = []

    def update(self, output: object) -> None:
        self.outputs.append(output)


class _FakeLangfuse:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.observations: list[dict] = []
        self.span = _FakeSpan()
        self.closed = False

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.observations.append(kwargs)
        yield self.span

    def shutdown(self) -> None:
        self.closed = True


def test_disabled_tracer_is_noop() -> None:
    tracer = setup_tracing(Settings(_env_file=None, langfuse_public_key=""))
    with tracer.trace("chat", {"q": 1}, {}) as set_output:
        set_output("ignored")
    tracer.shutdown()


def test_enabled_tracer_records_root_span(monkeypatch) -> None:
    instrumented: list[bool] = []
    monkeypatch.setattr(tracing, "Langfuse", _FakeLangfuse)
    monkeypatch.setattr(
        tracing.LlamaIndexInstrumentor, "instrument", lambda self: instrumented.append(True)
    )
    settings = Settings(
        _env_file=None, langfuse_public_key="pk", langfuse_secret_key="sk", langfuse_host="h"
    )

    tracer = setup_tracing(settings)
    with tracer.trace("chat", {"question": "q"}, {"repo": "a/b"}) as set_output:
        set_output({"answer": "x"})
    tracer.shutdown()

    client = tracer._client
    assert isinstance(client, _FakeLangfuse)
    assert client.kwargs == {"public_key": "pk", "secret_key": "sk", "host": "h"}
    assert client.observations[0]["name"] == "chat"
    assert client.observations[0]["metadata"] == {"repo": "a/b"}
    assert client.span.outputs == [{"answer": "x"}]
    assert client.closed
    assert instrumented == [True]


def test_tracer_without_client_yields_callable() -> None:
    with Tracer(None).trace("x", None, {}) as set_output:
        assert set_output(1) is None
