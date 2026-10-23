"""
LLM access for the UAE Labour Law RAG bot.

The provider is chosen in .env (LLM_PROVIDER=nebius | groq), so we can switch
models without changing code. Nebius uses the OpenAI API format, so we use
LangChain's ChatOpenAI class with Nebius' base URL.
"""
import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(), override=True)   # always read the newest .env values


def get_llm(temperature: float = 0, model: str | None = None):
    """Return the chat model chosen in .env. temperature=0 -> same answer each time (best for testing)."""
    provider = os.getenv("LLM_PROVIDER", "nebius")
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model or os.environ["GROQ_MODEL"], temperature=temperature)

    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model or os.environ["NEBIUS_MODEL"],
        base_url=os.environ["NEBIUS_BASE_URL"],
        api_key=os.environ["NEBIUS_API_KEY"],
        temperature=temperature,
    )
