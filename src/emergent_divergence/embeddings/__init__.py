"""Shared embedding layer.

A single ``Embedder`` is used for *all* semantic computations across every
backend so cross-backend numbers are comparable. MiniLM (``all-MiniLM-L6-v2``)
is the primary; a deterministic hashing embedding is the offline fallback.
"""

from __future__ import annotations

from emergent_divergence.embeddings.embedder import EMBED_DIM, Embedder, get_embedder

__all__ = ["EMBED_DIM", "Embedder", "get_embedder"]
