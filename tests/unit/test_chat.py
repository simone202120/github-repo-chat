from types import SimpleNamespace

import pytest

from github_repo_chat.core.chat import ChatEngine, ChatTurn, Usage, _usage_of
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.llm.prompts import NO_ANSWER
from tests.fakes import ScriptedLLM, StaticRetriever, chunk

REPO = RepoRef("octo", "demo")


def _engine(llm: ScriptedLLM, **kwargs) -> ChatEngine:
    return ChatEngine(llm, top_k=kwargs.pop("top_k", 2), history_turns=4, **kwargs)


def test_answer_without_history_still_rewrites_the_query_and_cites_sources() -> None:
    llm = ScriptedLLM(responses=["What does add do?", "It adds numbers [1]."])
    retriever = StaticRetriever([chunk("core.py", "def add(a, b): ...", "add", 3)])

    answer = _engine(llm).answer(REPO, retriever, "Cosa fa add?")

    assert answer.text == "It adds numbers [1]."
    assert [s.path for s in answer.sources] == ["core.py"]
    assert answer.standalone_question == "What does add do?"
    assert retriever.queries == ["What does add do?"]
    assert "(none)" in llm.prompts[0]
    assert "Latest question: Cosa fa add?" in llm.prompts[0]
    prompt = llm.prompts[1]
    assert "octo/demo" in prompt
    assert '<excerpt number="1" path="core.py" symbol="add" line="3">' in prompt
    assert "Question: Cosa fa add?" in prompt


def test_answer_with_history_condenses_before_retrieval() -> None:
    llm = ScriptedLLM(responses=["How is add tested?", "Answer [1]."])
    retriever = StaticRetriever([chunk("core.py", "code")])
    history = [ChatTurn("user", "What is add?"), ChatTurn("assistant", "A function.")]

    answer = _engine(llm).answer(REPO, retriever, "How is it tested?", history)

    assert retriever.queries == ["How is add tested?"]
    assert answer.standalone_question == "How is add tested?"
    assert "user: What is add?" in llm.prompts[0]
    assert "A function." in llm.prompts[1]


def test_answer_keeps_only_recent_history() -> None:
    llm = ScriptedLLM(responses=["q", "a"])
    history = [ChatTurn("user", f"turn {i}") for i in range(10)]
    _engine(llm).answer(REPO, StaticRetriever([chunk("a.py", "x")]), "next?", history)
    assert "turn 5" not in llm.prompts[0]
    assert "turn 6" in llm.prompts[0]


def test_answer_empty_condense_falls_back_to_question() -> None:
    llm = ScriptedLLM(responses=["  ", "a"])
    retriever = StaticRetriever([chunk("a.py", "x")])
    _engine(llm).answer(REPO, retriever, "original?", [ChatTurn("user", "hi")])
    assert retriever.queries == ["original?"]


def test_answer_without_context_skips_the_answer_call() -> None:
    llm = ScriptedLLM(responses=["Anything?"])
    answer = _engine(llm).answer(REPO, StaticRetriever([]), "Anything?")
    assert answer.text == NO_ANSWER
    assert answer.sources == []
    assert len(llm.prompts) == 1


def test_answer_empty_llm_reply_becomes_no_answer() -> None:
    answer = _engine(ScriptedLLM(responses=["q", ""])).answer(
        REPO, StaticRetriever([chunk("a.py", "x")]), "q"
    )
    assert answer.text == NO_ANSWER


def test_answer_truncates_to_top_k_without_reranker() -> None:
    nodes = [chunk(f"f{i}.py", "x") for i in range(5)]
    answer = _engine(ScriptedLLM(responses=["q", "a"])).answer(REPO, StaticRetriever(nodes), "q")
    assert [s.path for s in answer.sources] == ["f0.py", "f1.py"]


def test_answer_reranker_reorders_and_truncates() -> None:
    nodes = [chunk("low.py", "x"), chunk("high.py", "y"), chunk("mid.py", "z")]
    scores = {"x": 0.1, "y": 0.9, "z": 0.5}

    def reranker(query: str, passages: list[str]) -> list[float]:
        return [scores[p.splitlines()[-1]] for p in passages]

    engine = _engine(ScriptedLLM(responses=["q", "a"]), reranker=reranker)
    answer = engine.answer(REPO, StaticRetriever(nodes), "q")
    assert [s.path for s in answer.sources] == ["high.py", "mid.py"]
    assert answer.sources[0].score == pytest.approx(0.9)


def test_candidates_grow_when_reranking() -> None:
    assert _engine(ScriptedLLM()).candidates == 2
    assert _engine(ScriptedLLM(), reranker=lambda q, p: [0.0] * len(p)).candidates == 6


def test_answer_sums_usage_of_condense_and_answer_calls() -> None:
    usage = {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.001}
    llm = ScriptedLLM(responses=["standalone?", "a [1]"], usage=usage)
    answer = _engine(llm).answer(
        REPO, StaticRetriever([chunk("a.py", "x")]), "q", [ChatTurn("user", "hi")]
    )
    assert answer.usage.prompt_tokens == 200
    assert answer.usage.completion_tokens == 20
    assert answer.usage.cost_usd == pytest.approx(0.002)


def test_answer_usage_without_reported_cost() -> None:
    llm = ScriptedLLM(responses=["q", "a"], usage={"prompt_tokens": 5, "completion_tokens": 1})
    answer = _engine(llm).answer(REPO, StaticRetriever([chunk("a.py", "x")]), "q")
    assert (answer.usage.prompt_tokens, answer.usage.completion_tokens) == (10, 2)
    assert answer.usage.cost_usd is None


def test_answer_without_reported_usage_is_zero() -> None:
    answer = _engine(ScriptedLLM()).answer(REPO, StaticRetriever([]), "q")
    assert answer.usage == Usage()


def test_usage_of_reads_object_style_raw_response() -> None:
    raw = SimpleNamespace(usage=SimpleNamespace(cost=0.5))
    assert _usage_of({"prompt_tokens": 3, "completion_tokens": 2}, raw) == Usage(3, 2, 0.5)
    assert _usage_of({}, None) == Usage()
