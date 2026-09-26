import pytest
from pydantic import ValidationError

from github_repo_chat.config import Settings


def test_settings_tracing_disabled_without_langfuse_keys() -> None:
    settings = Settings(_env_file=None, langfuse_public_key="", langfuse_secret_key="")
    assert settings.tracing_enabled is False


def test_settings_tracing_enabled_with_langfuse_keys() -> None:
    settings = Settings(_env_file=None, langfuse_public_key="pk", langfuse_secret_key="sk")
    assert settings.tracing_enabled is True


def test_settings_reject_non_positive_limits() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, top_k=0)
