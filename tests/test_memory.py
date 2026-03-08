import os
import json
from memory import write_campaign_entity, list_memories


def test_write_and_list():
    ent = {
        "campaign_id": "test_campaign_1",
        "visual_vector": [0.1, 0.2, 0.3],
        "text_vector": [0.2, 0.1, 0.0],
        "visual_model": "clip-vit-b32",
        "text_model": "all-MiniLM-L6-v2",
        "context_metadata": {"trend": "test", "timestamp": "2026-02-04T12:00:00Z"},
        "performance_node": {"engagement": 10},
        "alignment_score": 0.5,
        "tags": ["test"],
        "source": "unittest"
    }
    write_campaign_entity(ent)
    mems = list_memories(5)
    assert any(m['campaign_id'] == 'test_campaign_1' for m in mems)
