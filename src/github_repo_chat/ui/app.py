"""Streamlit page: index repositories from the sidebar and chat with them, sources included."""

import time
from typing import Any

import streamlit as st

from github_repo_chat.config import get_settings
from github_repo_chat.ui import components
from github_repo_chat.ui.client import ApiClient, ApiError

EXAMPLE_REPOS = ["fastapi/fastapi", "pallets/flask", "langchain-ai/langgraph"]
EXAMPLE_QUESTIONS = [
    "What is this project for?",
    "How do I install and run it?",
    "Where is the main entry point implemented?",
]
_POLL_INTERVAL_S = 1.0
_MAX_WAIT_S = 30 * 60
_ACTIVE = ("queued", "indexing", "deleting")
_SELECTED = "selected_repo"


def _index(client: ApiClient, url: str, branch: str | None = None) -> None:
    """Starts ingestion and follows its progress until it is ready or failed."""
    job = client.add_repo(url, branch)
    with st.status(f"Indexing {job['repo']}", expanded=True) as status:
        bar = st.progress(0.0, text=components.STAGE_LABELS["queued"])
        deadline = time.monotonic() + _MAX_WAIT_S
        while True:
            info = client.repo(job["id"])
            bar.progress(components.progress_fraction(info), text=components.progress_text(info))
            if info["status"] not in _ACTIVE:
                break
            if time.monotonic() > deadline:
                status.update(label=f"Still indexing {info['repo']}", state="error")
                st.warning("This is taking unusually long. Check the API logs, then reload.")
                return
            time.sleep(_POLL_INTERVAL_S)
        if info["status"] == "failed":
            status.update(label=f"Indexing {info['repo']} failed", state="error")
            st.error(f"{info['error']}. Check the URL and branch, then try again.")
            return
        status.update(
            label=f"Indexed {info['repo']}: {info['file_count']} files, "
            f"{info['chunk_count']} chunks",
            state="complete",
            expanded=False,
        )
    st.session_state[_SELECTED] = info["id"]


def _sidebar(client: ApiClient) -> list[dict[str, Any]]:
    with st.sidebar:
        st.subheader("Add repository")
        with st.form("add_repo", clear_on_submit=True, border=False):
            url = st.text_input("GitHub URL or owner/name", placeholder="pallets/flask")
            branch = st.text_input("Branch", placeholder="default branch")
            submitted = st.form_submit_button("Index", type="primary", width="stretch")
        if submitted and url.strip():
            _index(client, url.strip(), branch.strip() or None)
        elif submitted:
            st.warning("Enter a GitHub URL such as `pallets/flask`.")

        repos = client.repos()
        st.subheader("Indexed repositories")
        if not repos:
            st.caption("Nothing indexed yet.")
        for info in repos:
            card = components.repo_card(info)
            if card.button("Delete", key=f"delete:{info['id']}", type="tertiary"):
                client.delete_repo(info["id"])
                st.session_state.pop(f"history:{info['id']}", None)
                st.rerun()
    return repos


def _empty_state(client: ApiClient) -> None:
    st.markdown("#### Start with a repository")
    st.write("Pick an example or paste any public GitHub URL in the sidebar.")
    for column, repo in zip(st.columns(len(EXAMPLE_REPOS)), EXAMPLE_REPOS, strict=True):
        if column.button(repo, key=f"example:{repo}", icon=":material/book:", width="stretch"):
            _index(client, repo)
            st.rerun()


def _pick_repo(repos: list[dict[str, Any]]) -> str | None:
    ready = [r for r in repos if r["status"] == "ready"]
    if not ready:
        st.info("Indexing in progress: the chat opens as soon as a repository is ready.")
        return None
    ids = [r["id"] for r in ready]
    labels = {r["id"]: r["repo"] for r in ready}
    current = st.session_state.get(_SELECTED)
    selected: str = st.selectbox(
        "Repository",
        ids,
        index=ids.index(current) if current in ids else 0,
        format_func=labels.__getitem__,
    )
    st.session_state[_SELECTED] = selected
    return selected


def _chat(client: ApiClient, repo_id: str) -> None:
    history: list[dict[str, Any]] = st.session_state.setdefault(f"history:{repo_id}", [])
    for message in history:
        with st.chat_message(message["role"]):
            if message["role"] == "assistant":
                components.assistant_reply(message["reply"])
            else:
                st.markdown(message["content"])

    question = st.chat_input("Ask about this repository")
    if not history:
        st.caption("Try one of these:")
        for column, example in zip(
            st.columns(len(EXAMPLE_QUESTIONS)), EXAMPLE_QUESTIONS, strict=True
        ):
            if column.button(example, key=f"question:{example}", width="stretch"):
                question = example
    if not question:
        return

    with st.chat_message("user"):
        st.markdown(question)
    turns = [{"role": m["role"], "content": m["content"]} for m in history]
    with st.chat_message("assistant"):
        with st.spinner("Retrieving context and generating the answer..."):
            reply = client.chat(repo_id, question, turns)
        components.assistant_reply(reply)
    history.append({"role": "user", "content": question})
    history.append({"role": "assistant", "content": reply["answer"], "reply": reply})


def main() -> None:
    st.set_page_config(page_title="GitHub Repo Chat", page_icon=":speech_balloon:", layout="wide")
    st.title("GitHub Repo Chat")
    st.caption(
        "Ask questions about any public GitHub repository. Answers cite the files they come from."
    )
    client = ApiClient(get_settings().api_url)
    try:
        repos = _sidebar(client)
        if not repos:
            _empty_state(client)
            return
        repo_id = _pick_repo(repos)
        if repo_id is not None:
            _chat(client, repo_id)
    except ApiError as error:
        st.error(components.friendly_error(error, client.base_url))


main()
