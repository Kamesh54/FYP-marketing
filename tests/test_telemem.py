from memory import write_campaign_entity
from telemem import deduplicate


def test_dedup_basic():
    # write two similar fake memories
    write_campaign_entity({
        "campaign_id": "tm_a",
        "text_vector": [0.9, 0.1, 0.0],
        "visual_vector": [0.8, 0.2],
        "performance_node": {"engagement": 5},
        "source": "unittest"
    })
    write_campaign_entity({
        "campaign_id": "tm_b",
        "text_vector": [0.89, 0.12, 0.01],
        "visual_vector": [0.79, 0.21],
        "performance_node": {"engagement": 3},
        "source": "unittest"
    })

    res = deduplicate(threshold=0.7)
    assert isinstance(res, dict)
