import pytest
from llama_index.core.schema import MetadataMode

from github_repo_chat.core.repo_ref import RepoRef
from github_repo_chat.core.splitting import SourceFile, Splitter

REPO = RepoRef("octo", "demo")


@pytest.fixture
def splitter() -> Splitter:
    return Splitter(code_max_chars=300, code_chunk_lines=40, text_chunk_tokens=64)


def _python_module(functions: int) -> str:
    body = "\n".join(
        f"def func_{i}(value):\n    '''Adds {i}.'''\n    return value + {i}\n"
        for i in range(functions)
    )
    return f"import os\n\n{body}\n\nclass Widget:\n    def render(self):\n        return 1\n"


def test_split_code_by_definitions_with_symbol_and_line(splitter: Splitter) -> None:
    text = _python_module(12)
    nodes = splitter.split(REPO, SourceFile("pkg/mod.py", text, "python"))
    assert len(nodes) > 1
    lines = text.splitlines()
    for node in nodes:
        meta = node.metadata
        first = node.text.strip().splitlines()[0]
        assert lines[meta["start_line"] - 1].strip() == first.strip()
        assert (
            meta["url"]
            == f"https://github.com/octo/demo/blob/HEAD/pkg/mod.py#L{meta['start_line']}"
        )
        assert meta["path"] == "pkg/mod.py"
        assert meta["language"] == "python"
        assert node.ref_doc_id == "pkg/mod.py"
    assert nodes[1].metadata["symbol"].startswith("func_")
    assert nodes[-1].metadata["symbol"] in {"Widget", "render"} or "Widget" in nodes[-1].text


def test_split_markdown_by_heading_sections(splitter: Splitter) -> None:
    text = "# Demo\n\nIntro.\n\n## Install\n\nRun pip install demo.\n\n## Usage\n\nCall demo().\n"
    nodes = splitter.split(REPO, SourceFile("README.md", text, "markdown"))
    assert [n.metadata["symbol"] for n in nodes] == ["Demo", "Install", "Usage"]
    assert [n.metadata["start_line"] for n in nodes] == [1, 5, 9]


def test_split_long_markdown_section_is_capped(splitter: Splitter) -> None:
    sentences = " ".join(f"Sentence number {i} explains a detail." for i in range(80))
    text = f"# Guide\n\n{sentences}\n"
    nodes = splitter.split(REPO, SourceFile("docs/guide.md", text, "markdown"))
    assert len(nodes) > 1
    assert all(n.metadata["symbol"] == "Guide" for n in nodes)


def test_split_unparsable_code_falls_back_to_text(splitter: Splitter) -> None:
    text = "}}}} ((( def broken\n" * 5
    nodes = splitter.split(REPO, SourceFile("bad.py", text, "python"))
    assert nodes
    assert "".join(n.text for n in nodes).count("broken") >= 5


def test_split_plain_text_uses_sentence_splitter(splitter: Splitter) -> None:
    nodes = splitter.split(REPO, SourceFile("notes.txt", "Hello world.\n", "text"))
    assert len(nodes) == 1
    assert nodes[0].metadata["symbol"] == ""
    assert nodes[0].metadata["start_line"] == 1


def test_split_empty_file_returns_no_nodes(splitter: Splitter) -> None:
    assert splitter.split(REPO, SourceFile("empty.py", "\n\n", "python")) == []


@pytest.mark.parametrize(
    ("language", "path", "code", "symbol"),
    [
        (
            "go",
            "main.go",
            "package main\n\nfunc (s *Server) Start() error {\n\treturn nil\n}\n",
            "Start",
        ),
        ("rust", "lib.rs", "pub fn parse(input: &str) -> u32 {\n    1\n}\n", "parse"),
        (
            "typescript",
            "a.ts",
            "export const load = async (id: string) => {\n  return id;\n};\n",
            "load",
        ),
        (
            "java",
            "A.java",
            "public class A {\n    public static int twice(int x) {\n"
            "        return 2 * x;\n    }\n}\n",
            "A",
        ),
    ],
)
def test_split_detects_symbols_across_languages(
    splitter: Splitter, language: str, path: str, code: str, symbol: str
) -> None:
    nodes = splitter.split(REPO, SourceFile(path, code, language))
    assert nodes[0].metadata["symbol"] == symbol


def test_split_embeds_path_and_symbol_but_not_url(splitter: Splitter) -> None:
    node = splitter.split(REPO, SourceFile("a.py", "def run():\n    pass\n", "python"))[0]
    embedded = node.get_content(metadata_mode=MetadataMode.EMBED)
    assert "a.py" in embedded
    assert "run" in embedded
    assert "https://" not in embedded


def test_split_detects_kotlin_fun_symbol(splitter: Splitter) -> None:
    """Kotlin declares functions with `fun`, not `func`/`fn`; the outline must recognise it."""
    code = "package demo\n\nfun twice(x: Int): Int {\n    return x * 2\n}\n"
    nodes = splitter.split(REPO, SourceFile("Main.kt", code, "kotlin"))
    assert nodes[0].metadata["symbol"] == "twice"


def test_split_start_line_is_correct_for_chunks_with_a_duplicate_first_line(
    splitter: Splitter,
) -> None:
    block = "def handler(event):\n" + "".join(f"    step_{i}(event)\n" for i in range(12))
    text = f"{block}\n{block}"
    nodes = splitter.split(REPO, SourceFile("dup.py", text, "python"))
    starts = [n.metadata["start_line"] for n in nodes if n.text.lstrip().startswith("def handler")]
    assert starts == [1, 15]
