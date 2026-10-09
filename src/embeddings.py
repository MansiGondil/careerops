"""
Local embedding generation. No API, no cost, and the resume never leaves
this machine — which matters because profile/ holds personal data.
"""
from functools import lru_cache

from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
DIMENSIONS = 384

# Model inputs are truncated at 256 word pieces. Job descriptions run far
# longer, so the text handed to encode() must be the part that carries
# signal, not boilerplate.
MAX_CHARS = 2000


@lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    """Loaded once per process; the first call takes a few seconds."""
    return SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]) -> list[list[float]]:
    """Encode a batch. Batching is substantially faster than one at a time."""
    model = get_model()
    vectors = model.encode(
        [t[:MAX_CHARS] for t in texts],
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,
    )
    return [v.tolist() for v in vectors]


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
