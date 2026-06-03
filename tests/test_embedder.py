"""Unit tests for the shared Embedder (brief §4.1)."""

from __future__ import annotations

import numpy as np

from emergent_divergence.embeddings.embedder import EMBED_DIM, Embedder, get_embedder


def test_embed_shape():
    emb = Embedder()
    out = emb.embed(["one", "two", "three"])
    assert out.shape == (3, EMBED_DIM)
    assert out.dtype == np.float32


def test_embed_empty_returns_zero_rows():
    out = Embedder().embed([])
    assert out.shape == (0, EMBED_DIM)


def test_embed_one_shape():
    v = Embedder().embed_one("a sentence about robustness")
    assert v.shape == (EMBED_DIM,)


def test_embed_l2_normalised():
    out = Embedder().embed(["incentives and falsifiability", "tail-risk dominates"])
    norms = np.linalg.norm(out, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)


def test_embed_deterministic():
    e1 = Embedder().embed(["same text here"])
    e2 = Embedder().embed(["same text here"])
    assert np.allclose(e1, e2)


def test_identical_text_cosine_is_one():
    out = Embedder().embed(["repeat me", "repeat me"])
    cos = float(np.dot(out[0], out[1]))  # already L2-normalised
    assert cos == np.float32(cos)
    assert abs(cos - 1.0) < 1e-5


def test_info_fields():
    info = Embedder().info()
    assert info["backend"] in ("minilm", "hashing-fallback")
    assert info["dim"] == EMBED_DIM
    assert "model_name" in info


def test_get_embedder_is_singleton():
    assert get_embedder() is get_embedder()
