"""Shared text embedder: MiniLM primary, deterministic hashing fallback.

All semantic divergence and semantic influence-delta numbers run through *one*
``Embedder`` instance per process so that cross-backend (Ollama vs Claude)
comparisons are apples-to-apples. The primary embedding is
``sentence-transformers`` ``all-MiniLM-L6-v2`` (384-d). If that cannot be
imported or loaded (no network, no torch wheel, etc.), we fall back to a
deterministic feature-hashing embedding of the same dimensionality that is
L2-normalised so cosine similarity is well-defined and responds to lexical
overlap. The active backend is recorded and disclosed in ``RUN_MANIFEST.json``
and the report; the fallback's limitations are stated there too.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np

EMBED_DIM = 384
_MODEL_NAME = "all-MiniLM-L6-v2"
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder:
    """Encode text to L2-normalised float32 vectors of dimension ``EMBED_DIM``.

    ``backend`` is ``"minilm"`` when sentence-transformers loaded, else
    ``"hashing-fallback"``. ``model_name`` is the resolved model identifier. Both
    are surfaced in the run manifest so the report can disclose which path ran.
    """

    def __init__(self, *, prefer: str = "minilm"):
        self.backend: str = "hashing-fallback"
        self.model_name: str = "hashing-fallback-384"
        self._model = None
        if prefer == "minilm":
            self._try_load_minilm()

    def _try_load_minilm(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except Exception:
            return
        try:
            self._model = SentenceTransformer(_MODEL_NAME)
            self.backend = "minilm"
            self.model_name = _MODEL_NAME
        except Exception:
            # Import worked but load failed (no weights / no network) — stay on fallback.
            self._model = None

    # ── public API ───────────────────────────────────────────────────────────

    @property
    def is_fallback(self) -> bool:
        """True when the semantic backend degraded to the lexical hashing path.

        Semantic divergence/influence numbers are only *semantic* on ``minilm``;
        on the fallback they reduce to lexical overlap. The pipeline gates real
        runs on this so a degraded embedder can't masquerade as semantic results.
        """
        return self.backend != "minilm"

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an ``(N, EMBED_DIM)`` float32 array of L2-normalised vectors."""
        if not texts:
            return np.empty((0, EMBED_DIM), dtype=np.float32)
        if self._model is not None:
            vecs = self._model.encode(
                texts, show_progress_bar=False, normalize_embeddings=True
            )
            return np.asarray(vecs, dtype=np.float32)
        return np.vstack([self._hash_embed(t) for t in texts]).astype(np.float32)

    def embed_one(self, text: str) -> np.ndarray:
        """Embed a single string -> ``(EMBED_DIM,)`` vector."""
        return self.embed([text])[0]

    def info(self) -> dict[str, str | int | bool]:
        return {
            "backend": self.backend,
            "model_name": self.model_name,
            "dim": EMBED_DIM,
            "is_fallback": self.is_fallback,
        }

    # ── deterministic fallback ─────────────────────────────────────────────────

    @staticmethod
    def _hash_embed(text: str) -> np.ndarray:
        """Deterministic signed feature-hashing embedding, L2-normalised.

        Unigrams and adjacent bigrams are hashed into ``EMBED_DIM`` buckets with a
        sign derived from a second hash. This gives a stable vector whose cosine
        similarity tracks lexical/structural overlap — crude but reproducible and
        fully offline. It is *not* semantically rich; the report says so.
        """
        vec = np.zeros(EMBED_DIM, dtype=np.float64)
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return vec.astype(np.float32)
        features = list(tokens)
        features += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        for feat in features:
            h = hashlib.sha1(feat.encode("utf-8")).digest()
            bucket = int.from_bytes(h[:4], "big") % EMBED_DIM
            sign = 1.0 if (h[4] & 1) else -1.0
            vec[bucket] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.astype(np.float32)


_SINGLETON: Embedder | None = None


def get_embedder(*, prefer: str = "minilm") -> Embedder:
    """Return a process-wide cached ``Embedder`` (loaded once)."""
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Embedder(prefer=prefer)
    return _SINGLETON
