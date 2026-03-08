"""
Graph Database Entity Schemas and Constants
Defines node labels, relationship types, and their properties.
"""

from enum import Enum
from typing import Dict, List, Any
from dataclasses import dataclass
from datetime import datetime

# ==================== NODE LABELS ====================

class NodeLabel(str, Enum):
    """Node labels used in the knowledge graph."""
    USER = "User"
    BRAND = "Brand"
    CAMPAIGN = "Campaign"
    CONTENT = "Content"
    KEYWORD = "Keyword"
    COMPETITOR = "Competitor"
    METRIC = "Metric"
    AGENT = "Agent"
    WORKFLOW = "Workflow"
    TOPIC = "Topic"
    MARKET = "Market"
    SEGMENT = "Segment"
    IMAGE = "Image"
    PROMPT_VERSION = "PromptVersion"
    CRITIC_LOG = "CriticLog"
    RESEARCH = "Research"


# ==================== RELATIONSHIP TYPES ====================

class RelationshipType(str, Enum):
    """Relationship types used in the knowledge graph."""
    
    # User relationships
    OWNS = "OWNS"
    MANAGES = "MANAGES"
    COLLABORATED_WITH = "COLLABORATED_WITH"
    
    # Brand relationships
    TARGETS = "TARGETS"
    COMPETES_WITH = "COMPETES_WITH"
    SIMILAR_TO = "SIMILAR_TO"
    OPERATES_IN = "OPERATES_IN"
    
    # Keyword relationships
    APPEARS_IN = "APPEARS_IN"
    SIMILAR_KEYWORD = "SIMILAR_KEYWORD"
    PARENT_KEYWORD = "PARENT_KEYWORD"
    
    # Content relationships
    PART_OF = "PART_OF"
    REFERENCES = "REFERENCES"
    LINKS_TO = "LINKS_TO"
    
    # Campaign relationships
    HAS_METRICS = "HAS_METRICS"
    HAS_CONTENT = "HAS_CONTENT"
    
    # Agent relationships
    EXECUTED_IN = "EXECUTED_IN"
    EXECUTED_BY = "EXECUTED_BY"
    
    # Workflow relationships
    OPTIMIZED_BY = "OPTIMIZED_BY"
    BASED_ON = "BASED_ON"
    
    # Performance relationships
    PERFORMS_WELL = "PERFORMS_WELL"
    PERFORMS_POORLY = "PERFORMS_POORLY"
    TRENDING = "TRENDING"

    # New agent relationships
    GENERATED_FROM = "GENERATED_FROM"   # Image GENERATED_FROM Content
    CRITIQUED_BY = "CRITIQUED_BY"       # Content CRITIQUED_BY CriticLog
    HAS_PROMPT = "HAS_PROMPT"           # Agent HAS_PROMPT PromptVersion
    PERFORMED_BEST = "PERFORMED_BEST"   # Brand/Campaign PERFORMED_BEST PromptVersion
    REJECTED_BY = "REJECTED_BY"         # Content REJECTED_BY User (HITL)
    RESEARCHED_BY = "RESEARCHED_BY"     # Topic RESEARCHED_BY Research


# ==================== NODE PROPERTIES ====================

class NodeSchema:
    """Schema definitions for each node type."""
    
    @staticmethod
    def get_user_schema() -> Dict[str, str]:
        """Schema for User nodes."""
        return {
            "user_id": "string",  # Unique identifier
            "email": "string",
            "name": "string",
            "tier": "string",  # e.g., "free", "premium", "enterprise"
            "created_at": "datetime",
            "updated_at": "datetime",
            "preferences": "json",
            "is_active": "boolean"
        }
    
    @staticmethod
    def get_brand_schema() -> Dict[str, str]:
        """Schema for Brand nodes."""
        return {
            "brand_id": "string",
            "brand_name": "string",
            "industry": "string",
            "website": "string",
            "description": "string",
            "target_audience": "string",
            "competitor_count": "integer",
            "market_position": "string",  # e.g., "leader", "challenger", "niche"
            "founded_year": "integer",
            "social_presence": "json",  # Links to social profiles
            "keywords_count": "integer",
            "created_at": "datetime",
            "updated_at": "datetime"
        }
    
    @staticmethod
    def get_campaign_schema() -> Dict[str, str]:
        """Schema for Campaign nodes."""
        return {
            "campaign_id": "string",
            "campaign_name": "string",
            "user_id": "string",
            "brand_id": "string",
            "campaign_type": "string",  # e.g., "content", "social", "seo"
            "objective": "string",
            "status": "string",  # e.g., "active", "paused", "completed"
            "budget": "float",
            "budget_spent": "float",
            "start_date": "datetime",
            "end_date": "datetime",
            "target_audience": "string",
            "metrics_summary": "json",  # Aggregated metrics
            "created_at": "datetime",
            "updated_at": "datetime"
        }
    
    @staticmethod
    def get_content_schema() -> Dict[str, str]:
        """Schema for Content nodes."""
        return {
            "content_id": "string",
            "content_type": "string",  # e.g., "blog", "social_post", "video"
            "title": "string",
            "description": "string",
            "body": "string",
            "platform": "string",  # e.g., "twitter", "instagram", "blog"
            "status": "string",  # e.g., "draft", "published", "archived"
            "seo_score": "float",
            "engagement_rate": "float",
            "impressions": "integer",
            "clicks": "integer",
            "conversions": "integer",
            "creator_agent": "string",
            "tags": "list",
            "keywords_used": "list",
            "published_at": "datetime",
            "created_at": "datetime",
            "updated_at": "datetime"
        }
    
    @staticmethod
    def get_keyword_schema() -> Dict[str, str]:
        """Schema for Keyword nodes."""
        return {
            "keyword_id": "string",
            "term": "string",
            "search_volume": "integer",
            "competition_level": "string",  # e.g., "low", "medium", "high"
            "difficulty_score": "float",  # 0-100
            "trend": "string",  # e.g., "rising", "stable", "declining"
            "cpc": "float",  # Cost per click
            "category": "string",
            "intent": "string",  # e.g., "informational", "commercial", "transactional"
            "seasonality": "float",  # 0-1
            "last_updated": "datetime",
            "created_at": "datetime"
        }
    
    @staticmethod
    def get_competitor_schema() -> Dict[str, str]:
        """Schema for Competitor nodes."""
        return {
            "competitor_id": "string",
            "competitor_name": "string",
            "domain": "string",
            "industry": "string",
            "market_share": "float",
            "employee_count": "integer",
            "founded_year": "integer",
            "top_keywords": "list",
            "keyword_count": "integer",
            "average_seo_score": "float",
            "content_count": "integer",
            "social_followers": "json",  # {platform: count}
            "threat_level": "string",  # e.g., "low", "medium", "high"
            "last_analyzed": "datetime",
            "created_at": "datetime",
            "updated_at": "datetime"
        }
    
    @staticmethod
    def get_metric_schema() -> Dict[str, str]:
        """Schema for Metric nodes."""
        return {
            "metric_id": "string",
            "platform": "string",  # e.g., "twitter", "instagram", "google_analytics"
            "metric_type": "string",  # e.g., "engagement", "reach", "conversion"
            "impressions": "integer",
            "clicks": "integer",
            "engagements": "integer",
            "shares": "integer",
            "comments": "integer",
            "conversions": "integer",
            "revenue": "float",
            "roi": "float",
            "engagement_rate": "float",
            "click_through_rate": "float",
            "conversion_rate": "float",
            "timestamp": "datetime",
            "period": "string"  # e.g., "daily", "weekly", "monthly"
        }
    
    @staticmethod
    def get_agent_schema() -> Dict[str, str]:
        """Schema for Agent nodes."""
        return {
            "agent_id": "string",
            "agent_type": "string",  # e.g., "content_agent", "seo_agent"
            "agent_name": "string",
            "specialization": "string",
            "success_rate": "float",  # 0-1
            "average_cost": "float",
            "execution_count": "integer",
            "avg_execution_time": "float",  # seconds
            "last_used": "datetime",
            "created_at": "datetime"
        }
    
    @staticmethod
    def get_workflow_schema() -> Dict[str, str]:
        """Schema for Workflow nodes."""
        return {
            "workflow_id": "string",
            "workflow_name": "string",
            "workflow_type": "string",  # e.g., "sequential", "parallel", "conditional"
            "total_cost": "float",
            "optimization_score": "float",  # 0-1
            "success_rate": "float",
            "execution_count": "integer",
            "estimated_time": "float",
            "avg_runtime": "float",
            "created_at": "datetime",
            "updated_at": "datetime"
        }


# ==================== RELATIONSHIP PROPERTIES ====================

class RelationshipSchema:
    """Schema definitions for relationships."""
    
    @staticmethod
    def get_owns_properties() -> Dict[str, str]:
        """Properties for OWNS relationship (User -> Brand)."""
        return {
            "since": "datetime",
            "role": "string"  # e.g., "owner", "manager"
        }
    
    @staticmethod
    def get_targets_properties() -> Dict[str, str]:
        """Properties for TARGETS relationship (Brand -> Keyword)."""
        return {
            "priority": "float",  # 0-1
            "confidence": "float",  # 0-1
            "added_date": "datetime"
        }
    
    @staticmethod
    def get_part_of_properties() -> Dict[str, str]:
        """Properties for PART_OF relationship (Content -> Campaign)."""
        return {
            "sequence": "integer",
            "contribution_to_goal": "float",  # 0-1
            "added_date": "datetime"
        }
    
    @staticmethod
    def get_appears_in_properties() -> Dict[str, str]:
        """Properties for APPEARS_IN relationship (Keyword -> Content)."""
        return {
            "frequency": "integer",
            "position": "integer",  # First, second, etc. appearance
            "prominence": "float"  # 0-1 based on position
        }
    
    @staticmethod
    def get_executed_in_properties() -> Dict[str, str]:
        """Properties for EXECUTED_IN relationship (Agent -> Workflow)."""
        return {
            "sequence": "integer",
            "cost": "float",
            "execution_time": "float",
            "status": "string",  # e.g., "success", "failed"
            "timestamp": "datetime"
        }


# ==================== CONTENT TYPE DEFINITIONS ====================

class ContentType(str, Enum):
    """Supported content types."""
    BLOG_POST = "blog_post"
    SOCIAL_POST = "social_post"
    VIDEO = "video"
    INFOGRAPHIC = "infographic"
    WHITEPAPER = "whitepaper"
    CASE_STUDY = "case_study"
    NEWSLETTER = "newsletter"
    PRODUCT_PAGE = "product_page"


class Platform(str, Enum):
    """Social media and publishing platforms."""
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    LINKEDIN = "linkedin"
    TIKTOK = "tiktok"
    REDDIT = "reddit"
    BLOG = "blog"
    WEBSITE = "website"
    EMAIL = "email"


class CampaignType(str, Enum):
    """Types of campaigns."""
    CONTENT = "content"
    SOCIAL = "social"
    SEO = "seo"
    PAID_ADS = "paid_ads"
    EMAIL = "email"
    INFLUENCER = "influencer"
    PR = "pr"


class CampaignStatus(str, Enum):
    """Campaign statuses."""
    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ContentStatus(str, Enum):
    """Content statuses."""
    DRAFT = "draft"
    REVIEW = "review"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class AgentType(str, Enum):
    """Types of agents in the system."""
    CONTENT_AGENT = "content_agent"
    SEO_AGENT = "seo_agent"
    KEYWORD_AGENT = "keyword_agent"
    COMPETITOR_AGENT = "competitor_agent"
    REDDIT_AGENT = "reddit_agent"
    METRICS_AGENT = "metrics_agent"
    ROUTER_AGENT = "router_agent"
    # New agents
    RESEARCH_AGENT = "research_agent"
    BRAND_AGENT = "brand_agent"
    IMAGE_AGENT = "image_agent"
    CRITIC_AGENT = "critic_agent"
    CAMPAIGN_AGENT = "campaign_agent"
    PROMPT_OPTIMIZER = "prompt_optimizer"


# ==================== DATACLASS DEFINITIONS ====================

@dataclass
class UserNode:
    """Represents a User node."""
    user_id: str
    email: str
    name: str
    tier: str = "free"
    created_at: str = None
    updated_at: str = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for graph operations."""
        return {
            "user_id": self.user_id,
            "email": self.email,
            "name": self.name,
            "tier": self.tier,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class BrandNode:
    """Represents a Brand node."""
    brand_id: str
    brand_name: str
    industry: str
    website: str
    created_at: str = None
    updated_at: str = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for graph operations."""
        return {
            "brand_id": self.brand_id,
            "brand_name": self.brand_name,
            "industry": self.industry,
            "website": self.website,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


@dataclass
class KeywordNode:
    """Represents a Keyword node."""
    keyword_id: str
    term: str
    search_volume: int = 0
    difficulty_score: float = 0.0
    created_at: str = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for graph operations."""
        return {
            "keyword_id": self.keyword_id,
            "term": self.term,
            "search_volume": self.search_volume,
            "difficulty_score": self.difficulty_score,
            "created_at": self.created_at
        }


# ==================== NEW NODE DATACLASSES ====================

@dataclass
class GeneratedImageNode:
    """Represents an AI-generated image linked to a content piece."""
    image_id: str
    content_id: str
    prompt_used: str
    runway_job_id: str = ""
    url: str = ""
    status: str = "pending"  # pending | completed | failed
    created_at: str = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "content_id": self.content_id,
            "prompt_used": self.prompt_used,
            "runway_job_id": self.runway_job_id,
            "url": self.url,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class PromptVersionNode:
    """Represents a versioned prompt stored in the graph for optimization tracking."""
    version_id: str
    agent_name: str
    context_type: str
    prompt_text: str
    performance_score: float = 0.0
    use_count: int = 0
    created_at: str = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "agent_name": self.agent_name,
            "context_type": self.context_type,
            "prompt_text": self.prompt_text[:500],  # truncate for graph storage
            "performance_score": self.performance_score,
            "use_count": self.use_count,
            "created_at": self.created_at,
        }


@dataclass
class CriticLogNode:
    """Represents a critic evaluation linked to a content node."""
    critic_log_id: str
    content_id: str
    intent_score: float
    brand_score: float
    quality_score: float
    overall_score: float
    passed: bool = False
    user_decision: str = "pending"  # pending | approved | rejected | edited
    created_at: str = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "critic_log_id": self.critic_log_id,
            "content_id": self.content_id,
            "intent_score": self.intent_score,
            "brand_score": self.brand_score,
            "quality_score": self.quality_score,
            "overall_score": self.overall_score,
            "passed": self.passed,
            "user_decision": self.user_decision,
            "created_at": self.created_at,
        }


# ==================== UTILITY FUNCTIONS ====================

def get_node_schema(label: NodeLabel) -> Dict[str, str]:
    """
    Get the schema for a specific node label.
    
    Args:
        label: Node label
    
    Returns:
        Dictionary with property names and types
    """
    schemas = {
        NodeLabel.USER: NodeSchema.get_user_schema(),
        NodeLabel.BRAND: NodeSchema.get_brand_schema(),
        NodeLabel.CAMPAIGN: NodeSchema.get_campaign_schema(),
        NodeLabel.CONTENT: NodeSchema.get_content_schema(),
        NodeLabel.KEYWORD: NodeSchema.get_keyword_schema(),
        NodeLabel.COMPETITOR: NodeSchema.get_competitor_schema(),
        NodeLabel.METRIC: NodeSchema.get_metric_schema(),
        NodeLabel.AGENT: NodeSchema.get_agent_schema(),
        NodeLabel.WORKFLOW: NodeSchema.get_workflow_schema(),
        NodeLabel.IMAGE: {
            "image_id": "string", "content_id": "string",
            "runway_job_id": "string", "url": "string",
            "status": "string", "created_at": "datetime",
        },
        NodeLabel.PROMPT_VERSION: {
            "version_id": "string", "agent_name": "string",
            "context_type": "string", "performance_score": "float",
            "use_count": "integer", "created_at": "datetime",
        },
        NodeLabel.CRITIC_LOG: {
            "critic_log_id": "string", "content_id": "string",
            "overall_score": "float", "passed": "boolean",
            "user_decision": "string", "created_at": "datetime",
        },
        NodeLabel.RESEARCH: {
            "domain": "string", "depth_level": "string",
            "created_at": "datetime", "expires_at": "datetime",
        },
    }
    return schemas.get(label, {})


def get_relationship_schema(rel_type: RelationshipType) -> Dict[str, str]:
    """
    Get the schema for a specific relationship type.
    
    Args:
        rel_type: Relationship type
    
    Returns:
        Dictionary with property names and types
    """
    schemas = {
        RelationshipType.OWNS: RelationshipSchema.get_owns_properties(),
        RelationshipType.TARGETS: RelationshipSchema.get_targets_properties(),
        RelationshipType.PART_OF: RelationshipSchema.get_part_of_properties(),
        RelationshipType.APPEARS_IN: RelationshipSchema.get_appears_in_properties(),
        RelationshipType.EXECUTED_IN: RelationshipSchema.get_executed_in_properties(),
    }
    return schemas.get(rel_type, {})


if __name__ == "__main__":
    """Display all schemas."""
    print("=" * 50)
    print("NODE SCHEMAS")
    print("=" * 50)
    for label in NodeLabel:
        print(f"\n{label.value}:")
        schema = get_node_schema(label)
        for prop, prop_type in schema.items():
            print(f"  - {prop}: {prop_type}")
    
    print("\n" + "=" * 50)
    print("RELATIONSHIP TYPES")
    print("=" * 50)
    for rel_type in RelationshipType:
        print(f"  - {rel_type.value}")
