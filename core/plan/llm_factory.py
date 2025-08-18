from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, Tuple


def have_llm_key() -> bool:
    """Return True if either OpenAI or Azure OpenAI key is present."""
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))


def build_chat_llm(*, temperature: float = 0.0, callbacks: Optional[list[Any]] = None) -> Tuple[Any, str]:
    """Construct a Chat LLM client configured from environment variables.

    Returns a tuple of (llm_instance, model_label_for_summary).

    Env variables:
      - Provider selection (optional):
        - KEIRI_AGENT_LLM_PROVIDER: "openai" | "azure" (auto if unset)

      - OpenAI (non-Azure):
        - OPENAI_API_KEY (required)
        - OPENAI_BASE_URL or OPENAI_API_BASE (optional)
        - OPENAI_ORG_ID or OPENAI_ORGANIZATION (optional)
        - KEIRI_AGENT_LLM_MODEL (optional, default "gpt-4.1")

      - Azure OpenAI:
        - AZURE_OPENAI_API_KEY (required)
        - AZURE_OPENAI_ENDPOINT (required)
        - AZURE_OPENAI_API_VERSION or OPENAI_API_VERSION (optional, default "2024-02-15-preview")
        - AZURE_OPENAI_DEPLOYMENT or KEIRI_AGENT_AZURE_DEPLOYMENT (required if provider=azure)
          If none is provided, falls back to KEIRI_AGENT_LLM_MODEL, then "gpt-4.1".
    """

    from langchain_openai import ChatOpenAI  # type: ignore

    provider = (os.getenv("KEIRI_AGENT_LLM_PROVIDER") or "").strip().lower()
    use_azure = provider == "azure"

    if use_azure:
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = (
            os.getenv("AZURE_OPENAI_API_VERSION")
            or os.getenv("OPENAI_API_VERSION")
            or "2024-02-15-preview"
        )
        deployment = (
            os.getenv("AZURE_OPENAI_DEPLOYMENT")
            or os.getenv("KEIRI_AGENT_AZURE_DEPLOYMENT")
            or os.getenv("KEIRI_AGENT_LLM_MODEL")
            or "gpt-4.1"
        )
        if not api_key or not endpoint:
            raise RuntimeError(
                "Azure OpenAI requires AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT"
            )

        # Use base_url style for broad compatibility across langchain_openai versions
        base_url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        # Some langchain_openai versions expect the Azure API version via headers rather than kwarg
        # Remove openai_api_version from kwargs passed to ChatOpenAI to avoid TypeError in old clients
        kwargs = {
            "model": deployment,
            "base_url": base_url,
            "api_key": api_key,
            "temperature": temperature,
        }
        # Expose version through environment for the OpenAI client
        os.environ.setdefault("OPENAI_API_VERSION", api_version)
        if callbacks is not None:
            kwargs["callbacks"] = callbacks
        llm = ChatOpenAI(**kwargs)
        return llm, f"azure:{deployment}"

    # Default: non-Azure OpenAI
    model_name = os.getenv("KEIRI_AGENT_LLM_MODEL") or "gpt-4.1"
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    org_id = os.getenv("OPENAI_ORG_ID") or os.getenv("OPENAI_ORGANIZATION")

    kwargs3: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
    }
    if api_key:
        kwargs3["api_key"] = api_key
    if base_url:
        kwargs3["base_url"] = base_url
    if org_id:
        kwargs3["organization"] = org_id
    if callbacks is not None:
        kwargs3["callbacks"] = callbacks
    llm = ChatOpenAI(**kwargs3)
    return llm, model_name


def build_text_embedder() -> Tuple[Callable[[List[str]], List[List[float]]], str]:
    """Construct an embeddings model from environment configuration.

    Returns a tuple of (embed_fn, model_label).
    The returned function accepts a list of texts and returns list of vectors.
    """

    from langchain_openai import OpenAIEmbeddings  # type: ignore

    provider = (os.getenv("KEIRI_AGENT_LLM_PROVIDER") or "").strip().lower()
    use_azure = provider == "azure"

    # Defaults
    default_model = os.getenv("KEIRI_AGENT_EMBED_MODEL") or "text-embedding-3-large"

    if use_azure:
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = (
            os.getenv("AZURE_OPENAI_API_VERSION")
            or os.getenv("OPENAI_API_VERSION")
            or "2024-02-15-preview"
        )
        deployment = (
            os.getenv("AZURE_OPENAI_EMBEDDINGS_DEPLOYMENT")
            or os.getenv("KEIRI_AGENT_AZURE_EMBED_DEPLOYMENT")
            or default_model
        )
        if not api_key or not endpoint:
            raise RuntimeError("Azure OpenAI embeddings requires AZURE_OPENAI_API_KEY and AZURE_OPENAI_ENDPOINT")
        base_url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        os.environ.setdefault("OPENAI_API_VERSION", api_version)
        embeddings = OpenAIEmbeddings(model=deployment, base_url=base_url, api_key=api_key)
        def _embed(texts: List[str]) -> List[List[float]]:
            return embeddings.embed_documents(texts)
        return _embed, f"azure-embed:{deployment}"

    # Default OpenAI
    model_name = default_model
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embeddings (or set provider=azure)")
    kwargs: dict[str, Any] = {"model": model_name, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    embeddings = OpenAIEmbeddings(**kwargs)
    def _embed(texts: List[str]) -> List[List[float]]:
        return embeddings.embed_documents(texts)
    return _embed, f"openai-embed:{model_name}"

