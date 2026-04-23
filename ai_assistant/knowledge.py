"""RAG knowledge base — store text with Voyage AI embeddings, search by similarity.

SQLite schema:
    knowledge(id, title, content, tags, embedding BLOB, created_at)

Embeddings stored as raw float32 bytes. Cosine similarity in-memory (fine
for <10k entries; switch to ANN if it grows beyond that).
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import numpy as np
import voyageai

from . import config

logger = logging.getLogger(__name__)


# Voyage context limit for voyage-3-lite is 32k tokens, but longer inputs
# hurt retrieval quality. Chunk on input side.
MAX_CHARS_PER_CHUNK = 4000


@dataclass
class KnowledgeEntry:
    id: int
    title: str
    content: str
    tags: str | None
    created_at: str
    similarity: float | None = None  # set when returned from search


def init_db() -> None:
    with sqlite3.connect(config.DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                tags       TEXT,
                embedding  BLOB    NOT NULL,
                created_at TEXT    NOT NULL
            )
            """
        )


def _client() -> voyageai.Client:
    if not config.VOYAGE_API_KEY:
        raise RuntimeError("VOYAGE_API_KEY not set — cannot use knowledge base.")
    return voyageai.Client(api_key=config.VOYAGE_API_KEY)


def _embed_document(text: str) -> np.ndarray:
    """Embed a document (for storage) using Voyage's `document` input type."""
    client = _client()
    result = client.embed(
        [text[:MAX_CHARS_PER_CHUNK]],
        model=config.VOYAGE_MODEL,
        input_type="document",
    )
    return np.asarray(result.embeddings[0], dtype=np.float32)


def _embed_query(text: str) -> np.ndarray:
    """Embed a query (for search) using Voyage's `query` input type."""
    client = _client()
    result = client.embed(
        [text], model=config.VOYAGE_MODEL, input_type="query"
    )
    return np.asarray(result.embeddings[0], dtype=np.float32)


def add_entry(title: str, content: str, tags: str | None = None) -> int:
    """Store a knowledge entry with its embedding. Returns new id."""
    embedding = _embed_document(f"{title}\n\n{content}")
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(config.DB_PATH) as conn:
        cur = conn.execute(
            "INSERT INTO knowledge(title, content, tags, embedding, created_at) "
            "VALUES (?,?,?,?,?)",
            (title, content, tags, embedding.tobytes(), now),
        )
        return cur.lastrowid


def delete_entry(entry_id: int) -> bool:
    with sqlite3.connect(config.DB_PATH) as conn:
        cur = conn.execute("DELETE FROM knowledge WHERE id = ?", (entry_id,))
        return cur.rowcount > 0


def list_entries(limit: int = 100) -> list[KnowledgeEntry]:
    with sqlite3.connect(config.DB_PATH) as conn:
        rows = conn.execute(
            "SELECT id, title, content, tags, created_at "
            "FROM knowledge ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        KnowledgeEntry(
            id=r[0], title=r[1], content=r[2], tags=r[3], created_at=r[4]
        )
        for r in rows
    ]


def search(query: str, top_k: int = 5, tag: str | None = None) -> list[KnowledgeEntry]:
    """Vector similarity search. Returns top_k entries, most similar first."""
    query_vec = _embed_query(query)
    query_vec /= np.linalg.norm(query_vec) + 1e-12

    sql = "SELECT id, title, content, tags, embedding, created_at FROM knowledge"
    params: tuple = ()
    if tag:
        sql += " WHERE tags LIKE ?"
        params = (f"%{tag}%",)

    with sqlite3.connect(config.DB_PATH) as conn:
        rows = conn.execute(sql, params).fetchall()

    if not rows:
        return []

    matrix = np.frombuffer(
        b"".join(r[4] for r in rows), dtype=np.float32
    ).reshape(len(rows), -1)
    # Normalize matrix rows
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-12
    matrix_normed = matrix / norms
    similarities = matrix_normed @ query_vec  # cosine similarity

    top_idx = np.argsort(-similarities)[:top_k]
    results: list[KnowledgeEntry] = []
    for i in top_idx:
        r = rows[i]
        results.append(
            KnowledgeEntry(
                id=r[0],
                title=r[1],
                content=r[2],
                tags=r[3],
                created_at=r[5],
                similarity=float(similarities[i]),
            )
        )
    return results


def format_search_result(entries: Iterable[KnowledgeEntry]) -> str:
    """For inclusion in LLM context."""
    lines = []
    for e in entries:
        sim_str = f" (유사도 {e.similarity:.2f})" if e.similarity is not None else ""
        lines.append(f"### [#{e.id}] {e.title}{sim_str}")
        if e.tags:
            lines.append(f"태그: {e.tags}")
        lines.append(e.content)
        lines.append("")
    return "\n".join(lines).strip()
