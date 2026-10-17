"""OpenAI-compatible embeddings for the optional RAG subsystem."""

from langchain_core.embeddings import Embeddings
from loguru import logger
from openai import OpenAI

from app.config import config


class OpenAICompatibleEmbeddings(Embeddings):
    """Embeddings client configured independently from the chat client."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        dimensions: int,
    ) -> None:
        self.client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
        self.model = model
        self.dimensions = dimensions
        logger.info(
            "Embeddings client initialized: model={}, dimensions={}, configured={}",
            model,
            dimensions,
            self.client is not None,
        )

    def _get_client(self) -> OpenAI:
        if self.client is None:
            raise RuntimeError(
                "RAG embeddings are not configured. Set EMBEDDING_API_KEY, "
                "EMBEDDING_BASE_URL, and EMBEDDING_MODEL. Chat models cannot "
                "be used as embeddings models."
            )
        return self.client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            response = self._get_client().embeddings.create(
                model=self.model,
                input=texts,
                dimensions=self.dimensions,
                encoding_format="float",
            )
            return [item.embedding for item in response.data]
        except Exception as exc:
            logger.error("Document embedding failed: {}", exc)
            raise RuntimeError(f"Document embedding failed: {exc}") from exc

    def embed_query(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Query text cannot be empty")

        try:
            response = self._get_client().embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions,
                encoding_format="float",
            )
            return response.data[0].embedding
        except Exception as exc:
            logger.error("Query embedding failed: {}", exc)
            raise RuntimeError(f"Query embedding failed: {exc}") from exc


vector_embedding_service = OpenAICompatibleEmbeddings(
    api_key=config.embedding_api_key,
    base_url=config.embedding_base_url,
    model=config.embedding_model,
    dimensions=config.embedding_dimensions,
)
