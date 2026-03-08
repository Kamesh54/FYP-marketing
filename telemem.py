"""
TeleMem: Narrative Dynamic Extraction for deduplication of campaign memories.
Simple clustering by cosine similarity on text + visual embeddings.
"""
import logging
import math
from typing import List, Dict, Any
import numpy as np
from memory import list_memories, write_campaign_entity, _chroma_text_collection, _chroma_vis_collection

logger = logging.getLogger(__name__)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def deduplicate(threshold: float = 0.88) -> Dict[str, Any]:
    """Run simple deduplication over recent memories.
    Groups memories with high combined similarity and mark merged entries.
    Returns a summary dict.
    """
    # Prefer using Chroma for nearest neighbors if available
    memories = list_memories(1000)
    clusters = []
    if _chroma_text_collection is not None or _chroma_vis_collection is not None:
        # Build a map of campaign_id -> memory
        mem_map = {m['campaign_id']: m for m in memories}
        visited = set()
        for m in memories:
            cid = m['campaign_id']
            if cid in visited:
                continue
            cluster = [m]
            visited.add(cid)
            # query chroma for similar text and visual (if vectors present)
            try:
                neighbors = []
                if m.get('text_vector') and _chroma_text_collection is not None:
                    resp = _chroma_text_collection.query(query_embeddings=[m['text_vector']], n_results=10, include=['metadatas','distances','ids'])
                    for ids in resp['ids']:
                        for vid in ids:
                            # metadata includes campaign_id
                            pass
                    # collect neighbor campaign ids from metadatas
                    for meta_row in resp.get('metadatas', [[]])[0]:
                        if meta_row and meta_row.get('campaign_id'):
                            neighbors.append(meta_row.get('campaign_id'))
                if m.get('visual_vector') and _chroma_vis_collection is not None:
                    resp2 = _chroma_vis_collection.query(query_embeddings=[m['visual_vector']], n_results=10, include=['metadatas','distances','ids'])
                    for meta_row in resp2.get('metadatas', [[]])[0]:
                        if meta_row and meta_row.get('campaign_id'):
                            neighbors.append(meta_row.get('campaign_id'))

                # Add neighbor memories to cluster if present in mem_map
                for nid in neighbors:
                    if nid in mem_map and nid not in visited:
                        cluster.append(mem_map[nid])
                        visited.add(nid)
            except Exception:
                # fallback to basic clustering if chroma query fails
                pass

            clusters.append(cluster)
    else:
        # fallback: linear clustering by combined similarity
        n = len(memories)
        assigned = [False] * n
        for i in range(n):
            if assigned[i]:
                continue
            base = memories[i]
            base_text = np.array(base.get('text_vector') or [])
            base_vis = np.array(base.get('visual_vector') or [])
            cluster = [base]
            assigned[i] = True
            for j in range(i+1, n):
                if assigned[j]:
                    continue
                other = memories[j]
                other_text = np.array(other.get('text_vector') or [])
                other_vis = np.array(other.get('visual_vector') or [])
                text_sim = _cosine(base_text, other_text) if base_text.size and other_text.size else 0.0
                vis_sim = _cosine(base_vis, other_vis) if base_vis.size and other_vis.size else 0.0
                combined = 0.7 * text_sim + 0.3 * vis_sim
                if combined >= threshold:
                    cluster.append(other)
                    assigned[j] = True

            clusters.append(cluster)

    # For each multi-item cluster, pick representative (highest engagement if present)
    merged = []
    for c in clusters:
        if len(c) == 1:
            continue
        # pick representative by performance_node.engagement or created_at
        best = None
        best_score = -math.inf
        for m in c:
            perf = m.get('performance_node') or {}
            score = perf.get('engagement', 0) or 0
            if score > best_score:
                best = m
                best_score = score

        # mark others as merged into best
        merged_ids = []
        for m in c:
            if m['id'] == best['id']:
                continue
            # update dedup info by rewriting with merged flag
            dedup = m.get('dedup_info') or {}
            dedup.update({"merged": True, "merged_into": best['id']})
            write_campaign_entity({
                "campaign_id": m['id'],
                "visual_vector": m.get('visual_vector'),
                "text_vector": m.get('text_vector'),
                "visual_model": m.get('visual_model'),
                "text_model": m.get('text_model'),
                "context_metadata": m.get('context_metadata'),
                "performance_node": m.get('performance_node'),
                "alignment_score": m.get('alignment_score'),
                "deduplication": dedup,
                "tags": m.get('tags'),
                "source": m.get('source')
            })
            merged_ids.append(m['id'])

        merged.append({
            "telemem_id": f"tm_{best['id']}",
            "representative_campaign_id": best['id'],
            "merged_campaigns": merged_ids,
            "merge_score": best_score
        })

    summary = {
        "clusters": len(clusters),
        "merged_clusters": len(merged),
        "merged_details": merged
    }
    logger.info(f"TeleMem dedup completed: {summary}")
    return summary
