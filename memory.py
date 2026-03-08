"""
Memory module: store CampaignEntity objects and optionally vectors.
Supports local JSON/SQLite-backed storage and optional Chroma/Weaviate integration.
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from database import get_db_connection

logger = logging.getLogger(__name__)

# --- Embedding Helper ---
_text_model = None

def get_text_embedding(text: str) -> List[float]:
    """Get embedding for text using sentence-transformers."""
    global _text_model
    try:
        from tools import embedding
        if _text_model is None:
            _text_model = embedding.load_text_model()
        
        # It returns a numpy array, convert to list
        params = embedding.embed_texts(_text_model, [text])
        return params[0].tolist()
    except Exception as e:
        logger.warning(f"Embedding failed (returning zero vector): {e}")
        return [0.0] * 384 # Fallback dimensionality

# Optional Chroma integration (graceful fallback if chromadb not installed)
_chroma_client = None
_chroma_text_collection = None
_chroma_vis_collection = None
try:
    import chromadb
    from chromadb.config import Settings

    def _init_chroma():
        global _chroma_client, _chroma_text_collection, _chroma_vis_collection
        if _chroma_client is not None:
            return
        # Use default in-process chroma (duckdb+parquet) unless CHROMA_SERVER is provided
        chroma_server = os.getenv('CHROMA_SERVER')
        if chroma_server:
            _chroma_client = chromadb.Client(Settings(chroma_api_impl="rest", chroma_server_host=chroma_server))
        else:
            _chroma_client = chromadb.Client()

        # Create / get two collections: text and visual
        try:
            _chroma_text_collection = _chroma_client.get_collection(name="campaign_text")
        except Exception:
            _chroma_text_collection = _chroma_client.create_collection(name="campaign_text")

        try:
            _chroma_vis_collection = _chroma_client.get_collection(name="campaign_visual")
        except Exception:
            _chroma_vis_collection = _chroma_client.create_collection(name="campaign_visual")

    _init_chroma()
except Exception:
    # chromadb not available; proceed without vector DB
    _chroma_client = None
    _chroma_text_collection = None
    _chroma_vis_collection = None


def ensure_table():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_memory (
            id TEXT PRIMARY KEY,
            campaign_id TEXT,
            visual_vector TEXT,
            text_vector TEXT,
            visual_model TEXT,
            text_model TEXT,
            context_metadata TEXT,
            performance_node TEXT,
            alignment_score REAL,
            dedup_info TEXT,
            tags TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)


def write_campaign_entity(entity: Dict[str, Any]) -> str:
    """Persist a CampaignEntity to the DB. Vectors are stored as JSON arrays.
    Returns the inserted id.
    """
    ensure_table()
    cid = entity.get("campaign_id") or f"campaign_{int(datetime.utcnow().timestamp())}"

    # If chroma available, push vectors into collections and store ids
    text_vec = entity.get("text_vector")
    vis_vec = entity.get("visual_vector")
    text_vec_id = None
    vis_vec_id = None
    if _chroma_client and _chroma_text_collection is not None and text_vec is not None:
        try:
            text_vec_id = f"text_{cid}"
            _chroma_text_collection.add(ids=[text_vec_id], embeddings=[text_vec], metadatas=[{"campaign_id": cid}])
        except Exception:
            logger.exception("Failed to add text vector to Chroma; falling back to DB storage")
            text_vec_id = None

    if _chroma_client and _chroma_vis_collection is not None and vis_vec is not None:
        try:
            vis_vec_id = f"vis_{cid}"
            _chroma_vis_collection.add(ids=[vis_vec_id], embeddings=[vis_vec], metadatas=[{"campaign_id": cid}])
        except Exception:
            logger.exception("Failed to add visual vector to Chroma; falling back to DB storage")
            vis_vec_id = None

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO campaign_memory
        (id, campaign_id, visual_vector, text_vector, visual_model, text_model, context_metadata, performance_node, alignment_score, dedup_info, tags, source, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cid,
            cid,
            json.dumps(vis_vec) if (vis_vec is not None and vis_vec_id is None) else json.dumps({"chroma_id": vis_vec_id}) if vis_vec_id else None,
            json.dumps(text_vec) if (text_vec is not None and text_vec_id is None) else json.dumps({"chroma_id": text_vec_id}) if text_vec_id else None,
            entity.get("visual_model"),
            entity.get("text_model"),
            json.dumps(entity.get("context_metadata")) if entity.get("context_metadata") else json.dumps({}),
            json.dumps(entity.get("performance_node")) if entity.get("performance_node") else json.dumps({}),
            float(entity.get("alignment_score")) if entity.get("alignment_score") is not None else None,
            json.dumps(entity.get("deduplication")) if entity.get("deduplication") else json.dumps({}),
            json.dumps(entity.get("tags")) if entity.get("tags") else json.dumps([]),
            entity.get("source"),
            entity.get("created_at") or datetime.utcnow().isoformat()
        ))

    logger.info(f"Wrote campaign memory {cid} (text_vec_id={text_vec_id}, vis_vec_id={vis_vec_id})")
    return cid


def list_memories(limit: int = 100) -> List[Dict[str, Any]]:
    ensure_table()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campaign_memory ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        out = []
        for r in rows:
            out.append({
                k: (json.loads(r[k]) if k in ("visual_vector", "text_vector", "context_metadata", "performance_node", "dedup_info", "tags") and r[k] else r[k])
                for k in r.keys()
            })
        return out


def find_similar_by_text(text_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
    """Naive linear search for similar text vectors (cosine similarity)."""
    import numpy as np
    # If chroma is available, use it
    if _chroma_client and _chroma_text_collection is not None:
        try:
            resp = _chroma_text_collection.query(query_embeddings=[text_vector], n_results=top_k, include=['metadatas', 'distances', 'ids'])
            docs = []
            for i, ids in enumerate(resp['ids']):
                for j, vid in enumerate(ids):
                    meta = resp['metadatas'][i][j]
                    # retrieve campaign memory record for metadata.campaign_id
                    campaign_id = meta.get('campaign_id')
                    # fetch DB record
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT * FROM campaign_memory WHERE campaign_id = ?', (campaign_id,))
                        row = cursor.fetchone()
                        if row:
                            doc = {k: (json.loads(row[k]) if k in ("visual_vector", "text_vector", "context_metadata", "performance_node", "dedup_info", "tags") and row[k] else row[k]) for k in row.keys()}
                            docs.append(doc)
            return docs[:top_k]
        except Exception:
            logger.exception("Chroma text query failed, falling back to DB scan")

    memories = list_memories(1000)
    q = np.array(text_vector)
    results = []
    for m in memories:
        tv = m.get('text_vector')
        if not tv:
            continue
        v = np.array(tv)
        denom = (np.linalg.norm(q) * np.linalg.norm(v))
        sim = float(np.dot(q, v) / denom) if denom > 0 else 0.0
        results.append((sim, m))
    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:top_k]]


def find_similar_by_visual(visual_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
    # Prefer chroma visual collection
    import numpy as np
    if _chroma_client and _chroma_vis_collection is not None:
        try:
            resp = _chroma_vis_collection.query(query_embeddings=[visual_vector], n_results=top_k, include=['metadatas', 'distances', 'ids'])
            docs = []
            for i, ids in enumerate(resp['ids']):
                for j, vid in enumerate(ids):
                    meta = resp['metadatas'][i][j]
                    campaign_id = meta.get('campaign_id')
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('SELECT * FROM campaign_memory WHERE campaign_id = ?', (campaign_id,))
                        row = cursor.fetchone()
                        if row:
                            doc = {k: (json.loads(row[k]) if k in ("visual_vector", "text_vector", "context_metadata", "performance_node", "dedup_info", "tags") and row[k] else row[k]) for k in row.keys()}
                            docs.append(doc)
            return docs[:top_k]
        except Exception:
            logger.exception("Chroma visual query failed, falling back to DB scan")

    return find_similar_by_text(visual_vector, top_k=top_k)
