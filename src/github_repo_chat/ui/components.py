"""Streamlit rendering helpers: progress, repo cards, source cards, run metrics, errors."""

from typing import Any, Literal

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from github_repo_chat.ui.client import ApiError

STAGE_LABELS = {
    "queued": "Waiting to start",
    "downloading": "Downloading the repository archive",
    "filtering": "Selecting docs and source files",
    "splitting": "Splitting files into chunks",
    "embedding": "Embedding chunks",
    "done": "Done",
}
BadgeColor = Literal["green", "blue", "orange", "red", "gray"]
_STATUS_COLORS: dict[str, BadgeColor] = {
    "ready": "green",
    "queued": "blue",
    "indexing": "blue",
    "deleting": "orange",
    "failed": "red",
}


def progress_text(info: dict[str, Any]) -> str:
    stage = info.get("stage") or info["status"]
    label = STAGE_LABELS.get(stage, str(stage).capitalize())
    total = info.get("progress_total") or 0
    return f"{label} ({info['progress_done']}/{total})" if total else label


def progress_fraction(info: dict[str, Any]) -> float:
    total = info.get("progress_total") or 0
    return min(info["progress_done"] / total, 1.0) if total else 0.0


def friendly_error(error: ApiError, api_url: str) -> str:
    """Tells the user what went wrong and what to do about it."""
    if error.status is None:
        return (
            f"Cannot reach the backend at {api_url}. Start it with `docker compose up` "
            "(or `uv run uvicorn github_repo_chat.api.main:app`) and reload the page."
        )
    if error.status == 404:
        return f"{error} Index the repository from the sidebar first."
    if error.status == 409:
        return f"{error} Wait for the current operation to finish."
    if error.status == 422:
        return f"Please check the input: {error}"
    return f"The backend failed to answer ({error.status}): {error}. Check the API logs and retry."


def repo_card(info: dict[str, Any]) -> DeltaGenerator:
    """Bordered card with the repo status; returned so the caller can add actions inside."""
    card = st.container(border=True)
    with card:
        st.markdown(f"**{info['repo']}**" + (f" · `{info['branch']}`" if info["branch"] else ""))
        st.badge(info["status"], color=_STATUS_COLORS.get(info["status"], "gray"))
        st.caption(f"{info['file_count']} files · {info['chunk_count']} chunks")
        if info.get("error"):
            st.caption(f":red[{info['error']}]")
    return card


def source_cards(sources: list[dict[str, Any]]) -> None:
    if not sources:
        return
    st.caption("Sources")
    for source in sources:
        with st.container(border=True):
            title, link = st.columns([4, 1], vertical_alignment="center")
            symbol = f" · `{source['symbol']}`" if source["symbol"] else ""
            score = f" · score {source['score']:.2f}" if source["score"] is not None else ""
            title.markdown(
                f"**[{source['number']}]** `{source['path']}`:{source['start_line']}{symbol}{score}"
            )
            link.link_button("Open on GitHub", source["url"], width="stretch")


def run_metrics(reply: dict[str, Any]) -> None:
    usage = reply["usage"]
    cost = usage["cost_usd"]
    tokens, price, latency = st.columns(3)
    tokens.metric("Tokens", f"{usage['prompt_tokens'] + usage['completion_tokens']:,}")
    price.metric("Cost", f"${cost:.5f}" if cost is not None else "n/a")
    latency.metric("Latency", f"{reply['latency_ms'] / 1000:.1f} s")
    if reply.get("trace_url"):
        st.markdown(f"[View the Langfuse trace]({reply['trace_url']})")


def assistant_reply(reply: dict[str, Any]) -> None:
    st.markdown(reply["answer"])
    source_cards(reply["sources"])
    run_metrics(reply)
    with st.expander("Raw response", expanded=False):
        st.json(reply)
