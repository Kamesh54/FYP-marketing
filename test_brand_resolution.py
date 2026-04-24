from langgraph_nodes import _extract_brand_from_message, _resolve_brand_seed


def test_extract_brand_from_used_phrase():
    assert _extract_brand_from_message("I used Hercules for this report") == "Hercules"


def test_extract_brand_from_called_phrase():
    assert _extract_brand_from_message("The product is called Hercules Roadeo") == "Hercules Roadeo"


def test_resolve_brand_prefers_message_over_active_brand():
    state = {
        "user_message": "I used Hercules for this report",
        "active_brand": "Hero Cycles",
        "brand_info": {"brand_name": "Hero Cycles"},
        "extracted_params": {},
    }

    assert _resolve_brand_seed(state) == "Hercules"


def test_resolve_brand_skips_campaign_theme_when_active_brand_exists():
    state = {
        "user_message": "Create an Instagram post for Weekend Sale",
        "active_brand": "Hercules",
        "brand_info": {"brand_name": "Hercules"},
        "extracted_params": {"brand_name": "Weekend Sale", "platform": "instagram"},
    }

    assert _resolve_brand_seed(state) == "Hercules"
