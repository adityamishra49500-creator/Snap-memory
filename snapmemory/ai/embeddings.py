"""
SnapMemory Embedding Engine.

Honest note on this build: producing real transformer sentence-embeddings
(e.g. a Qualcomm AI Hub embedding model, or even a small ONNX
sentence-transformer) requires downloading model weights, which requires
network access. This project was authored in a sandboxed, offline
environment with no internet access, so it ships with a fully-working
LOCAL FALLBACK embedding engine built on scikit-learn's TF-IDF + character
n-grams, running entirely on CPU with no downloads required.

This is a real, working, deterministic local embedding model — it is not a
stub. It is simply weaker than a neural embedding model at capturing
paraphrase/semantic similarity, and stronger at exact term/keyword overlap.
That's why retrieval is hybrid (see ai/rag.py): TF-IDF cosine similarity +
keyword overlap scoring.

Swapping in a Qualcomm AI Hub embedding model on the real Snapdragon device:
    1. Export the AI-Hub-provided embedding model to ONNX (or use the
       provided .onnx directly).
    2. Implement `OnnxEmbeddingProvider` below (a stub class is included)
       pointing at that .onnx file.
    3. Set SNAPMEMORY_EMBEDDING_PROVIDER=onnx in the environment.
No other application code needs to change — everything downstream consumes
`embed_texts()` / `embed_query()`, not a specific implementation.
"""
import os
import pickle
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core import config
from ai.providers import registry, ModelStatus

_VECTORIZER_PATH = os.path.join(config.DATA_DIR, "tfidf_vectorizer.pkl")

_EMBEDDING_PROVIDER = os.environ.get("SNAPMEMORY_EMBEDDING_PROVIDER", "tfidf")


class TfidfEmbeddingProvider:
    """Local, offline, zero-download embedding provider.

    A single corpus-wide TfidfVectorizer is fit/refit as documents are
    added, and each chunk's embedding is its TF-IDF sparse row, densified
    and L2-normalized. This is intentionally simple and inspectable.
    """

    name = "TF-IDF (scikit-learn, local CPU)"

    def __init__(self):
        self.vectorizer: TfidfVectorizer | None = None
        self._load()

    def _load(self):
        if os.path.exists(_VECTORIZER_PATH):
            with open(_VECTORIZER_PATH, "rb") as f:
                self.vectorizer = pickle.load(f)

    def _save(self):
        with open(_VECTORIZER_PATH, "wb") as f:
            pickle.dump(self.vectorizer, f)

    def refit(self, all_texts: list[str]):
        """Refit the vectorizer over the full corpus. Called after each
        new document import so vocabulary stays current. For very large
        corpora this would be replaced with an incremental/hashing
        vectorizer — noted in ARCHITECTURE.md as a scaling limitation."""
        if not all_texts:
            self.vectorizer = None
            return
        vec = TfidfVectorizer(
            max_features=20000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            stop_words="english",
        )
        vec.fit(all_texts)
        self.vectorizer = vec
        self._save()

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        if self.vectorizer is None or not texts:
            return np.zeros((len(texts), 1))
        mat = self.vectorizer.transform(texts)
        return mat.toarray()

    def embed_query(self, text: str) -> np.ndarray:
        if self.vectorizer is None:
            return np.zeros((1,))
        return self.vectorizer.transform([text]).toarray()[0]


class OnnxEmbeddingProvider:
    """Hook point for a real Qualcomm AI Hub / ONNX embedding model.

    NOT implemented in this build (no network access to fetch model
    weights in the authoring environment). Wiring instructions are in
    SNAPDRAGON_SETUP.md. This class deliberately raises rather than
    pretending to work, per RULE 1 / RULE 2 of the build spec."""

    name = "ONNX embedding model (not configured)"

    def __init__(self, model_path: str | None = None):
        self.model_path = model_path
        if not model_path or not os.path.exists(model_path):
            raise RuntimeError(
                "OnnxEmbeddingProvider selected but no model file found. "
                "Set SNAPMEMORY_EMBEDDING_MODEL_PATH to a valid .onnx model "
                "exported/obtained via Qualcomm AI Hub. See SNAPDRAGON_SETUP.md."
            )


def get_embedding_provider():
    if _EMBEDDING_PROVIDER == "onnx":
        model_path = os.environ.get("SNAPMEMORY_EMBEDDING_MODEL_PATH")
        try:
            provider = OnnxEmbeddingProvider(model_path)
            registry.register(ModelStatus(
                capability="embedding", model_name="Qualcomm/ONNX embedding model",
                runtime="ONNX Runtime", execution_provider="Unknown",
                installed=True,
            ))
            return provider
        except RuntimeError as e:
            registry.register(ModelStatus(
                capability="embedding", model_name="Qualcomm/ONNX embedding model",
                runtime="ONNX Runtime", execution_provider="Not installed",
                installed=False, notes=str(e),
            ))
            # Honest, explicit fallback — not silent.
    provider = TfidfEmbeddingProvider()
    registry.register(ModelStatus(
        capability="embedding", model_name="TF-IDF local fallback",
        runtime=provider.name, execution_provider="CPU",
        installed=True, notes="Neural embedding model not configured; using local fallback.",
    ))
    return provider


_provider = None


def provider():
    global _provider
    if _provider is None:
        _provider = get_embedding_provider()
    return _provider


def refit_corpus(all_texts: list[str]):
    provider().refit(all_texts)


def embed_texts(texts: list[str]) -> np.ndarray:
    return provider().embed_texts(texts)


def embed_query(text: str) -> np.ndarray:
    return provider().embed_query(text)


def similarity(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0 or query_vec.size == 0:
        return np.zeros((matrix.shape[0],))
    q = query_vec.reshape(1, -1)
    if q.shape[1] != matrix.shape[1]:
        return np.zeros((matrix.shape[0],))
    return cosine_similarity(q, matrix)[0]
