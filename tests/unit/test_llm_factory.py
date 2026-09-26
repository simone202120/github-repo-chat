from github_repo_chat.config import Settings
from github_repo_chat.llm import factory
from github_repo_chat.llm.factory import build_llm, build_reranker


def test_build_llm_uses_openrouter_settings() -> None:
    settings = Settings(_env_file=None, openrouter_api_key="key", llm_model="vendor/model")
    llm = build_llm(settings)
    assert llm.metadata.model_name == "vendor/model"
    assert llm.api_key == "key"
    assert llm.api_base == "https://openrouter.ai/api/v1"


def test_build_reranker_disabled_by_default() -> None:
    assert build_reranker(Settings(_env_file=None)) is None


def test_build_reranker_scores_passages(monkeypatch) -> None:
    class _Encoder:
        def __init__(self, model_name: str) -> None:
            self.model_name = model_name

        def rerank(self, query: str, documents: list[str]):
            return iter(float(len(d)) for d in documents)

    monkeypatch.setattr(factory, "TextCrossEncoder", _Encoder)
    rerank = build_reranker(Settings(_env_file=None, rerank_model="tiny"))
    assert rerank is not None
    assert rerank("q", ["a", "abc"]) == [1.0, 3.0]
