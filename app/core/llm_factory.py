"""Factory for the application's Anthropic-compatible chat model."""

from typing import Any

from langchain_anthropic import ChatAnthropic

from app.config import config


class LLMFactory:
    """Create the Anthropic-compatible client used by chat and AIOps workflows."""

    @staticmethod
    def create_chat_model(
        model: str | None = None,
        temperature: float = 0.7,
        streaming: bool = True,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> ChatAnthropic:
        model = model or config.rag_model or config.anthropic_model
        base_url = base_url or config.anthropic_base_url
        api_key = api_key or config.anthropic_api_key

        if not api_key or api_key == "your-anthropic-api-key":
            raise ValueError("ANTHROPIC_API_KEY is not configured")

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key,
            max_retries=2,
        )


def content_to_text(content: Any) -> str:
    """Extract user-visible text from string or Anthropic content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


llm_factory = LLMFactory()
