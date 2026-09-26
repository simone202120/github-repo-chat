import pytest

from github_repo_chat.core.chat import ChatEngine, ChatTurn
from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.llm.prompts import NO_ANSWER
from tests.fakes import ScriptedLLM, StaticRetriever, chunk

REPO = RepoRef("octo", "demo")


def _engine(llm: ScriptedLLM, **kwargs) -> ChatEngine:
    return ChatEngine(llm, top_k=kwargs.pop("top_k", 2), history_turns=4, **kwargs)


def test_answer_without_history_skips_condensing_and_cites_sources() -> None:
    llm = ScriptedLLM(responses=["It adds numbers [1]."])
    retriever = StaticRetriever([chunk("core.py", "def add(a, b): ...", "add", 3)])

    answer = _engine(llm).answer(REPO, retriever, "What does add do?")

    assert answer.text == "It adds numbers [1]."
    assert [s.path for s in answer.sources] == ["core.py"]
    assert answer.standalone_question == "What does add do?"
    assert retriever.queries == ["What does add do?"]
    assert len(llm.prompts) == 1
    prompt = llm.prompts[0]
    assert "octo/demo" in prompt
    assert '<excerpt number="1" path="core.py" symbol="add" line="3">' in prompt
    assert "Question: What does add do?" in prompt


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


def test_answer_without_context_does_not_call_llm() -> None:
    llm = ScriptedLLM()
    answer = _engine(llm).answer(REPO, StaticRetriever([]), "Anything?")
    assert answer.text == NO_ANSWER
    assert answer.sources == []
    assert llm.prompts == []


def test_answer_empty_llm_reply_becomes_no_answer() -> None:
    answer = _engine(ScriptedLLM(responses=[""])).answer(
        REPO, StaticRetriever([chunk("a.py", "x")]), "q"
    )
    assert answer.text == NO_ANSWER


def test_answer_truncates_to_top_k_without_reranker() -> None:
    nodes = [chunk(f"f{i}.py", "x") for i in range(5)]
    answer = _engine(ScriptedLLM(responses=["a"])).answer(REPO, StaticRetriever(nodes), "q")
    assert [s.path for s in answer.sources] == ["f0.py", "f1.py"]


def test_answer_reranker_reorders_and_truncates() -> None:
    nodes = [chunk("low.py", "x"), chunk("high.py", "y"), chunk("mid.py", "z")]
    scores = {"x": 0.1, "y": 0.9, "z": 0.5}

    def reranker(query: str, passages: list[str]) -> list[float]:
        return [scores[p.splitlines()[-1]] for p in passages]

    engine = _engine(ScriptedLLM(responses=["a"]), reranker=reranker)
    answer = engine.answer(REPO, StaticRetriever(nodes), "q")
    assert [s.path for s in answer.sources] == ["high.py", "mid.py"]
    assert answer.sources[0].score == pytest.approx(0.9)


def test_candidates_grow_when_reranking() -> None:
    assert _engine(ScriptedLLM()).candidates == 2
    assert _engine(ScriptedLLM(), reranker=lambda q, p: [0.0] * len(p)).candidates == 6
