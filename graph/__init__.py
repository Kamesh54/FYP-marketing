"""
Graph module initialization and exports.
"""

from .graph_database import (
    GraphDatabaseClient,
    get_graph_client,
    initialize_graph_db,
    close_graph_db,
    is_graph_db_available,
)

from .graph_entities import (
    NodeLabel,
    RelationshipType,
    NodeSchema,
    RelationshipSchema,
    ContentType,
    Platform,
    CampaignType,
    CampaignStatus,
    ContentStatus,
    AgentType,
    UserNode,
    BrandNode,
    KeywordNode,
    GeneratedImageNode,
    PromptVersionNode,
    CriticLogNode,
    get_node_schema,
    get_relationship_schema,
)

from .graph_mapper import (
    GraphMapper,
    get_graph_mapper,
)

from .dual_write_helper import (
    DualWriteManager,
    get_dual_write_manager,
    sync_new_user,
    sync_new_brand,
    sync_new_campaign,
    sync_new_content,
    sync_new_keyword,
    sync_new_competitor,
    sync_new_metric,
    create_kg_relationship,
)

from .graph_queries import (
    GraphQueries,
    get_graph_queries,
)
from .graph_context import (
    get_brand_knowledge_context,
    format_kg_context_for_prompt,
)

__all__ = [
    # Database client
    "GraphDatabaseClient",
    "get_graph_client",
    "initialize_graph_db",
    "close_graph_db",
    "is_graph_db_available",
    
    # Entities and schemas
    "NodeLabel",
    "RelationshipType",
    "NodeSchema",
    "RelationshipSchema",
    "ContentType",
    "Platform",
    "CampaignType",
    "CampaignStatus",
    "ContentStatus",
    "AgentType",
    "UserNode",
    "BrandNode",
    "KeywordNode",
    "get_node_schema",
    "get_relationship_schema",
    
    # Mapper
    "GraphMapper",
    "get_graph_mapper",
    
    # Dual-write pattern
    "DualWriteManager",
    "get_dual_write_manager",
    "sync_new_user",
    "sync_new_brand",
    "sync_new_campaign",
    "sync_new_content",
    "sync_new_keyword",
    "sync_new_competitor",
    "sync_new_metric",
    "create_kg_relationship",
    
    # Graph queries
    "GraphQueries",
    "get_graph_queries",
]
