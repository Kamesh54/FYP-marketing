"""
Database Layer for Multi-Agent Application
SQLite-based persistence with connection pooling
"""
import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from threading import Lock

logger = logging.getLogger(__name__)

# Database file path
DB_PATH = "database/app.db"
DB_VERSION = 1
from graph import (
    sync_new_user,
    sync_new_brand,
    sync_new_campaign,
    sync_new_content,
    sync_new_metric,
    create_kg_relationship,
)

# Thread-safe connection pool
_connection_lock = Lock()

@contextmanager
def get_db_connection():
    """Context manager for database connections with automatic commit/rollback."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def initialize_database():
    """Create all database tables if they don't exist."""
    import os
    os.makedirs("database", exist_ok=True)
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            preferences TEXT DEFAULT '{}'
        )
        """)
        
        # Sessions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT 'New Chat',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            context_summary TEXT,
            is_active BOOLEAN DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        
        # Messages table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            formatted_content TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
        """)
        
        # Generated content table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_content (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('blog', 'post', 'image')),
            content TEXT NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
            preview_url TEXT,
            final_url TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
        """)

        # Workflow variant tracking table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_variants (
            option_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            content_id TEXT NOT NULL,
            workflow_name TEXT NOT NULL,
            state_hash TEXT NOT NULL,
            label TEXT,
            metadata TEXT DEFAULT '{}',
            is_selected INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
            FOREIGN KEY (content_id) REFERENCES generated_content(id) ON DELETE CASCADE
        )
        """)
        
        # Social posts table (for tracking published posts)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS social_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('twitter', 'instagram', 'facebook', 'linkedin')),
            post_id TEXT,
            post_url TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (content_id) REFERENCES generated_content(id) ON DELETE CASCADE
        )
        """)
        
        # Agent costs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT UNIQUE NOT NULL,
            token_cost REAL DEFAULT 0,
            time_cost REAL DEFAULT 0,
            api_cost_per_call REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Execution metrics table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS execution_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            execution_time REAL NOT NULL,
            tokens_used INTEGER DEFAULT 0,
            cost REAL DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
        """)
        
        # Social metrics table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS social_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('twitter', 'instagram', 'facebook', 'linkedin')),
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            impressions INTEGER DEFAULT 0,
            reach INTEGER DEFAULT 0,
            engagement_rate REAL DEFAULT 0,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (content_id) REFERENCES generated_content(id) ON DELETE CASCADE
        )
        """)
        
        # RL state table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS rl_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state_vector TEXT NOT NULL,
            action_taken TEXT NOT NULL,
            reward REAL NOT NULL,
            next_state_vector TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Q-table for Q-learning (deprecated - kept for backward compatibility)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS q_table (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            state_hash TEXT NOT NULL,
            action TEXT NOT NULL,
            q_value REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(state_hash, action)
        )
        """)
        
        # MABO Coordination State table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS mabo_coordination_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            iteration INTEGER NOT NULL,
            coordination_vars TEXT NOT NULL,
            lagrange_multipliers TEXT NOT NULL,
            budget_allocations TEXT NOT NULL,
            total_budget REAL NOT NULL,
            convergence_threshold REAL DEFAULT 0.0001,
            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(iteration)
        )
        """)
        
        # MABO Local BO State table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS mabo_local_bo_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            observed_points TEXT NOT NULL,
            observed_values TEXT NOT NULL,
            best_point TEXT,
            best_value REAL DEFAULT 999999.0,
            iteration INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(agent_name)
        )
        """)
        
        # MABO Reward Queue table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS mabo_reward_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL,
            state_hash TEXT NOT NULL,
            action TEXT NOT NULL,
            expected_delay_hours REAL NOT NULL,
            reward REAL,
            engagement_rate REAL,
            cost REAL,
            execution_time REAL,
            content_approved INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            stabilized_at TIMESTAMP,
            is_stabilized INTEGER DEFAULT 0,
            UNIQUE(content_id)
        )
        """)
        
        # Budget Allocator Campaign State table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS budget_allocator_campaigns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL,
            total_budget_spent REAL DEFAULT 0.0,
            total_clicks INTEGER DEFAULT 0,
            total_impressions INTEGER DEFAULT 0,
            observations TEXT,
            is_censored INTEGER DEFAULT 0,
            parameters TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(campaign_id)
        )
        """)
        
        # Validation Metrics table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS validation_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_type TEXT NOT NULL,
            value REAL NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Campaigns table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            status TEXT DEFAULT 'planning' CHECK(status IN ('planning', 'active', 'completed', 'paused')),
            start_date TIMESTAMP,
            end_date TIMESTAMP,
            budget_tier TEXT,
            strategy TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # Campaign Agenda table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_agenda (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            campaign_id TEXT NOT NULL,
            scheduled_time TIMESTAMP NOT NULL,
            action TEXT NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')),
            content_id TEXT,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE,
            FOREIGN KEY (content_id) REFERENCES generated_content(id) ON DELETE SET NULL
        )
        """)
        
        # Create indexes for MABO tables
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mabo_coordination_iter ON mabo_coordination_state(iteration)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mabo_local_bo_agent ON mabo_local_bo_state(agent_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mabo_reward_content ON mabo_reward_queue(content_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_mabo_reward_stabilized ON mabo_reward_queue(is_stabilized)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_budget_campaign ON budget_allocator_campaigns(campaign_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_validation_metrics_type ON validation_metrics(metric_type, timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_variants_state ON workflow_variants(state_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_user ON campaigns(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_campaign_agenda_campaign ON campaign_agenda(campaign_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_campaign_agenda_status ON campaign_agenda(status)")
        
        # Brand profiles table (extended)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS brand_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            brand_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            target_audience TEXT DEFAULT '',
            tone TEXT DEFAULT 'professional',
            industry TEXT,
            tagline TEXT,
            website_url TEXT,
            location TEXT,
            contacts TEXT,
            logo_url TEXT,
            colors TEXT DEFAULT '[]',
            fonts TEXT DEFAULT '[]',
            tone_preference TEXT DEFAULT 'professional',
            auto_extracted INTEGER DEFAULT 0,
            learned_signals TEXT DEFAULT '{}',
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id, brand_name)
        )
        """)

        # Prompt versions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompt_versions (
            id TEXT PRIMARY KEY,
            agent_name TEXT NOT NULL,
            context_type TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            performance_score REAL,
            use_count INTEGER DEFAULT 0,
            langsmith_run_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Critic logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS critic_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_id TEXT NOT NULL,
            session_id TEXT,
            intent_score REAL NOT NULL,
            brand_score REAL NOT NULL,
            quality_score REAL NOT NULL,
            overall_score REAL NOT NULL,
            critique_text TEXT NOT NULL,
            passed INTEGER NOT NULL DEFAULT 0,
            user_decision TEXT CHECK(user_decision IN ('approved', 'rejected', 'regenerated', NULL)),
            langsmith_run_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (content_id) REFERENCES generated_content(id) ON DELETE CASCADE
        )
        """)

        # Campaign schedules table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS campaign_schedules (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('twitter', 'instagram', 'linkedin', 'reddit', 'all')),
            content_template TEXT NOT NULL,
            trigger_type TEXT NOT NULL CHECK(trigger_type IN ('once', 'recurring')),
            run_at TIMESTAMP,
            cron_expr TEXT,
            status TEXT DEFAULT 'active' CHECK(status IN ('active', 'paused', 'completed', 'cancelled')),
            last_run TIMESTAMP,
            next_run TIMESTAMP,
            run_count INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """)

        # Research cache table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS research_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            depth_level TEXT NOT NULL CHECK(depth_level IN ('deep', 'medium', 'short')),
            result_json TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            UNIQUE(domain, depth_level)
        )
        """)

        # HITL events table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hitl_events (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            event_type TEXT NOT NULL CHECK(event_type IN ('content_approval', 'brand_info_needed', 'url_needed', 'critic_review')),
            payload TEXT NOT NULL,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'responded', 'expired')),
            response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            responded_at TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
        """)

        # Workflow runs table (track full pipeline executions)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workflow_runs (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            workflow_name TEXT NOT NULL,
            agent_sequence TEXT NOT NULL,
            agent_settings TEXT DEFAULT '{}',
            status TEXT DEFAULT 'running' CHECK(status IN ('running', 'completed', 'failed', 'waiting_hitl')),
            current_step INTEGER DEFAULT 0,
            steps_output TEXT DEFAULT '{}',
            langsmith_run_id TEXT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_content_session ON generated_content(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_content ON social_metrics(content_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_q_table_lookup ON q_table(state_hash, action)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_brand_user ON brand_profiles(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_prompt_versions_agent ON prompt_versions(agent_name, context_type)")

        # ── Schema migrations: add columns that may be missing in older DBs ──
        _brand_cols = {
            "description":      "TEXT DEFAULT ''",
            "target_audience":  "TEXT DEFAULT ''",
            "tone":             "TEXT DEFAULT 'professional'",
            "industry":         "TEXT",
            "tagline":          "TEXT",
            "website_url":      "TEXT",
            "location":         "TEXT",
            "contacts":         "TEXT",
            "logo_url":         "TEXT",
            "colors":           "TEXT DEFAULT '[]'",
            "fonts":            "TEXT DEFAULT '[]'",
            "tone_preference":  "TEXT DEFAULT 'professional'",
            "auto_extracted":   "INTEGER DEFAULT 0",
            "learned_signals":  "TEXT DEFAULT '{}'",
            "metadata":         "TEXT DEFAULT '{}'",
            "updated_at":       "TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        }
        cursor.execute("PRAGMA table_info(brand_profiles)")
        existing_cols = {row[1] for row in cursor.fetchall()}
        for col, col_def in _brand_cols.items():
            if col not in existing_cols:
                cursor.execute(f"ALTER TABLE brand_profiles ADD COLUMN {col} {col_def}")
                logger.info(f"Migration: added brand_profiles.{col}")
        # ────────────────────────────────────────────────────────────────────
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_critic_logs_content ON critic_logs(content_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_campaign_schedules_user ON campaign_schedules(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_research_cache_domain ON research_cache(domain, depth_level)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_hitl_events_session ON hitl_events(session_id, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_workflow_runs_session ON workflow_runs(session_id)")
        
        # Initialize default agent costs
        default_costs = [
            ('webcrawler', 0.0001, 10, 0),
            ('seo_agent', 0.0001, 30, 0),
            ('keyword_extractor', 0.0005, 15, 0),
            ('gap_analyzer', 0.001, 20, 0.005),
            ('content_agent_blog', 0.002, 25, 0),
            ('content_agent_social', 0.0005, 10, 0),
            ('image_generator', 0, 45, 0.05),
            ('social_poster', 0, 5, 0)
        ]
        
        for agent_name, token_cost, time_cost, api_cost in default_costs:
            cursor.execute("""
            INSERT OR IGNORE INTO agent_costs (agent_name, token_cost, time_cost, api_cost_per_call)
            VALUES (?, ?, ?, ?)
            """, (agent_name, token_cost, time_cost, api_cost))
        
        logger.info(f"Database initialized successfully at {DB_PATH}")

# ==================== USER OPERATIONS ====================

def create_user(email: str, password_hash: str) -> int:
    """Create a new user and return user_id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO users (email, password_hash, created_at)
        VALUES (?, ?, ?)
        """, (email, password_hash, datetime.now()))
        user_id = cursor.lastrowid
        # Non-blocking sync to Neo4j (pass minimal user info)
        try:
            sync_new_user({"id": user_id, "email": email, "created_at": datetime.now().isoformat()}, user_id)
        except Exception:
            logger.exception("Failed to sync new user to Neo4j")
        return user_id

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user by email address."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_last_login(user_id: int):
    """Update user's last login timestamp."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE users SET last_login = ? WHERE id = ?
        """, (datetime.now(), user_id))

# ==================== SESSION OPERATIONS ====================

def create_session(session_id: str, user_id: int, title: str = "New Chat") -> str:
    """Create a new session for a user."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO sessions (id, user_id, title, created_at, last_active)
        VALUES (?, ?, ?, ?, ?)
        """, (session_id, user_id, title, datetime.now(), datetime.now()))
        return session_id

def get_session(session_id: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Get session by ID, optionally verifying user ownership."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if user_id:
            cursor.execute("""
            SELECT * FROM sessions WHERE id = ? AND user_id = ? AND is_active = 1
            """, (session_id, user_id))
        else:
            cursor.execute("SELECT * FROM sessions WHERE id = ? AND is_active = 1", (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_sessions(user_id: int, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Get all sessions for a user, ordered by last_active."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM sessions 
        WHERE user_id = ? AND is_active = 1 
        ORDER BY last_active DESC 
        LIMIT ? OFFSET ?
        """, (user_id, limit, offset))
        return [dict(row) for row in cursor.fetchall()]

def update_session_activity(session_id: str):
    """Update session's last_active timestamp."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE sessions SET last_active = ? WHERE id = ?
        """, (datetime.now(), session_id))

def update_session_title(session_id: str, title: str):
    """Update session title."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE sessions SET title = ? WHERE id = ?
        """, (title, session_id))

def update_session_context(session_id: str, context_summary: str):
    """Update session context summary."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE sessions SET context_summary = ? WHERE id = ?
        """, (context_summary, session_id))

def delete_session(session_id: str, user_id: int):
    """Soft delete a session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE sessions SET is_active = 0 WHERE id = ? AND user_id = ?
        """, (session_id, user_id))

# ==================== MESSAGE OPERATIONS ====================

def save_message(session_id: str, role: str, content: str, formatted_content: Optional[str] = None):
    """Save a message to the database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO messages (session_id, role, content, formatted_content, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """, (session_id, role, content, formatted_content, datetime.now()))

def get_session_messages(session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get all messages for a session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if limit:
            cursor.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """, (session_id, limit))
        else:
            cursor.execute("""
            SELECT * FROM messages 
            WHERE session_id = ? 
            ORDER BY timestamp ASC
            """, (session_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_recent_messages(session_id: str, count: int = 10) -> List[Dict[str, Any]]:
    """Get the most recent N messages for a session."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM messages 
        WHERE session_id = ? 
        ORDER BY timestamp DESC 
        LIMIT ?
        """, (session_id, count))
        messages = [dict(row) for row in cursor.fetchall()]
        return list(reversed(messages))  # Return in chronological order

# ==================== CONTENT OPERATIONS ====================

def save_generated_content(content_id: str, session_id: str, content_type: str, 
                          content: str, preview_url: Optional[str] = None,
                          metadata: Optional[Dict] = None) -> str:
    """Save generated content (blog/post)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        metadata_json = json.dumps(metadata) if metadata else '{}'
        cursor.execute("""
        INSERT INTO generated_content (id, session_id, type, content, preview_url, metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (content_id, session_id, content_type, content, preview_url, metadata_json, datetime.now()))
        # Sync to Neo4j (non-blocking)
        try:
            sync_new_content({
                "id": content_id,
                "session_id": session_id,
                "type": content_type,
                "content": content,
                "preview_url": preview_url,
                "metadata": metadata or {},
                "created_at": datetime.now().isoformat()
            }, content_id)
        except Exception:
            logger.exception("Failed to sync generated content to Neo4j")
        return content_id

def update_content_metadata(content_id: str, metadata_updates: Dict[str, Any]):
    """Merge updates into generated content metadata."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT metadata FROM generated_content WHERE id = ?", (content_id,))
        row = cursor.fetchone()
        if not row:
            return
        current_metadata = json.loads(row[0]) if row[0] else {}
        current_metadata.update(metadata_updates)
        cursor.execute("""
        UPDATE generated_content SET metadata = ? WHERE id = ?
        """, (json.dumps(current_metadata), content_id))

def save_workflow_variant(option_id: str, session_id: str, content_id: str,
                          workflow_name: str, state_hash: str,
                          label: Optional[str] = None,
                          metadata: Optional[Dict[str, Any]] = None):
    """Persist workflow variant metadata."""
    metadata_json = json.dumps(metadata or {})
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO workflow_variants
        (option_id, session_id, content_id, workflow_name, state_hash, label, metadata, is_selected, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 
                COALESCE((SELECT is_selected FROM workflow_variants WHERE option_id = ?), 0),
                COALESCE((SELECT created_at FROM workflow_variants WHERE option_id = ?), ?))
        """, (
            option_id,
            session_id,
            content_id,
            workflow_name,
            state_hash,
            label,
            metadata_json,
            option_id,
            option_id,
            datetime.now()
        ))

def get_workflow_variant(option_id: str) -> Optional[Dict[str, Any]]:
    """Fetch workflow variant by option id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workflow_variants WHERE option_id = ?", (option_id,))
        row = cursor.fetchone()
        if row:
            data = dict(row)
            data['metadata'] = json.loads(data['metadata']) if data['metadata'] else {}
            return data
        return None

def get_workflow_variants(session_id: str, state_hash: str) -> List[Dict[str, Any]]:
    """Get all variants for a given session/state hash."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM workflow_variants
        WHERE session_id = ? AND state_hash = ?
        ORDER BY created_at ASC
        """, (session_id, state_hash))
        variants = []
        for row in cursor.fetchall():
            data = dict(row)
            data['metadata'] = json.loads(data['metadata']) if data['metadata'] else {}
            variants.append(data)
        return variants

def mark_variant_selection(option_id: str, is_selected: bool):
    """Mark a workflow variant as selected or not."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE workflow_variants SET is_selected = ? WHERE option_id = ?
        """, (1 if is_selected else 0, option_id))

def clear_variant_selection(session_id: str, state_hash: str, exclude_option_id: Optional[str] = None):
    """Clear selection flags for all variants in a group, optionally excluding one."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if exclude_option_id:
            cursor.execute("""
            UPDATE workflow_variants
            SET is_selected = 0
            WHERE session_id = ? AND state_hash = ? AND option_id != ?
            """, (session_id, state_hash, exclude_option_id))
        else:
            cursor.execute("""
            UPDATE workflow_variants
            SET is_selected = 0
            WHERE session_id = ? AND state_hash = ?
            """, (session_id, state_hash))
def get_generated_content(content_id: str) -> Optional[Dict[str, Any]]:
    """Get generated content by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM generated_content WHERE id = ?", (content_id,))
        row = cursor.fetchone()
        if row:
            content = dict(row)
            content['metadata'] = json.loads(content['metadata'])
            return content
        return None

def update_content_status(content_id: str, status: str, final_url: Optional[str] = None):
    """Update content status (pending/approved/rejected)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if final_url:
            cursor.execute("""
            UPDATE generated_content SET status = ?, final_url = ? WHERE id = ?
            """, (status, final_url, content_id))
        else:
            cursor.execute("""
            UPDATE generated_content SET status = ? WHERE id = ?
            """, (status, content_id))

# ==================== METRICS OPERATIONS ====================

def log_execution_metrics(session_id: str, agent_name: str, execution_time: float,
                          tokens_used: int = 0, cost: float = 0):
    """Log agent execution metrics."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO execution_metrics (session_id, agent_name, execution_time, tokens_used, cost, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, agent_name, execution_time, tokens_used, cost, datetime.now()))

def save_social_metrics(content_id: str, platform: str, likes: int = 0, comments: int = 0,
                       shares: int = 0, impressions: int = 0, reach: int = 0):
    """Save social media metrics for content."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        engagement_rate = (likes + comments + shares) / max(impressions, 1) * 100
        cursor.execute("""
        INSERT INTO social_metrics 
        (content_id, platform, likes, comments, shares, impressions, reach, engagement_rate, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (content_id, platform, likes, comments, shares, impressions, reach, engagement_rate, datetime.now()))
        metric_id = cursor.lastrowid
        # Sync metric to Neo4j and link to content
        try:
            sync_new_metric({
                "id": metric_id,
                "content_id": content_id,
                "platform": platform,
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "impressions": impressions,
                "reach": reach,
                "engagement_rate": engagement_rate,
                "timestamp": datetime.now().isoformat()
            }, metric_id)
            create_kg_relationship(content_id, metric_id, 'HAS_METRICS')
        except Exception:
            logger.exception("Failed to sync social metrics to Neo4j")

def get_social_metrics(content_id: Optional[str] = None, user_id: Optional[int] = None,
                       platform: Optional[str] = None, days: int = 30) -> List[Dict[str, Any]]:
    """Get social metrics with optional filters."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        query = """
        SELECT sm.* FROM social_metrics sm
        JOIN generated_content gc ON sm.content_id = gc.id
        JOIN sessions s ON gc.session_id = s.id
        WHERE sm.timestamp >= datetime('now', '-' || ? || ' days')
        """
        params = [days]
        
        if content_id:
            query += " AND sm.content_id = ?"
            params.append(content_id)
        if user_id:
            query += " AND s.user_id = ?"
            params.append(user_id)
        if platform:
            query += " AND sm.platform = ?"
            params.append(platform)
        
        query += " ORDER BY sm.timestamp DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

# ==================== BRAND PROFILE OPERATIONS ====================

def save_brand_profile(user_id: int, brand_name: str,
                      description: Optional[str] = None,
                      target_audience: Optional[str] = None,
                      tone: Optional[str] = None,
                      contacts: Optional[str] = None,
                      location: Optional[str] = None, logo_url: Optional[str] = None,
                      industry: Optional[str] = None, tagline: Optional[str] = None,
                      website_url: Optional[str] = None, colors: Optional[List] = None,
                      fonts: Optional[List] = None, tone_preference: Optional[str] = None,
                      auto_extracted: bool = False, learned_signals: Optional[Dict] = None,
                      metadata: Optional[Dict] = None) -> int:
    """Save or update brand profile for user (full extended version)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        metadata_json = json.dumps(metadata or {})
        colors_json   = json.dumps(colors or [])
        fonts_json    = json.dumps(fonts or [])
        learned_json  = json.dumps(learned_signals or {})

        cursor.execute("SELECT id FROM brand_profiles WHERE user_id = ? AND brand_name = ?", (user_id, brand_name))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
            UPDATE brand_profiles
            SET description=?, target_audience=?, tone=?,
                contacts=?, location=?, logo_url=?, industry=?, tagline=?,
                website_url=?, colors=?, fonts=?, tone_preference=?, auto_extracted=?,
                learned_signals=?, metadata=?, updated_at=?
            WHERE user_id=? AND brand_name=?
            """, (description, target_audience, tone or 'professional',
                  contacts, location, logo_url, industry, tagline,
                  website_url, colors_json, fonts_json, tone_preference or 'professional',
                  1 if auto_extracted else 0, learned_json, metadata_json, datetime.now(),
                  user_id, brand_name))
            return existing[0]
        else:
            cursor.execute("""
            INSERT INTO brand_profiles
                (user_id, brand_name, description, target_audience, tone,
                 contacts, location, logo_url, industry, tagline,
                 website_url, colors, fonts, tone_preference, auto_extracted,
                 learned_signals, metadata, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (user_id, brand_name, description, target_audience, tone or 'professional',
                  contacts, location, logo_url, industry, tagline,
                  website_url, colors_json, fonts_json, tone_preference or 'professional',
                  1 if auto_extracted else 0, learned_json, metadata_json, datetime.now()))
            brand_id = cursor.lastrowid
            try:
                sync_new_brand({
                    "id": brand_id, "user_id": user_id, "brand_name": brand_name,
                    "industry": industry, "metadata": metadata or {}
                }, brand_id)
            except Exception:
                logger.exception("Failed to sync brand to Neo4j")
            return brand_id

def get_brand_profile(user_id: int, brand_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Get brand profile for user, optionally by brand name."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if brand_name:
            cursor.execute("SELECT * FROM brand_profiles WHERE user_id = ? AND brand_name = ?", (user_id, brand_name))
        else:
            cursor.execute("SELECT * FROM brand_profiles WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1", (user_id,))
        row = cursor.fetchone()
        if row:
            profile = dict(row)
            for field in ('metadata', 'learned_signals'):
                if profile.get(field):
                    try:
                        profile[field] = json.loads(profile[field])
                    except Exception:
                        profile[field] = {}
            for field in ('colors', 'fonts'):
                if profile.get(field):
                    try:
                        profile[field] = json.loads(profile[field])
                    except Exception:
                        profile[field] = []
            return profile
        return None

def update_brand_profile(user_id: int, brand_name: Optional[str] = None, **kwargs) -> bool:
    """Partial update of brand profile — pass only fields to change."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if brand_name:
            cursor.execute("SELECT * FROM brand_profiles WHERE user_id = ? AND brand_name = ?", (user_id, brand_name))
        else:
            cursor.execute("SELECT * FROM brand_profiles WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1", (user_id,))
        existing = cursor.fetchone()

        if not existing:
            brand_name_to_create = brand_name or kwargs.pop('brand_name', None)
            if brand_name_to_create:
                save_brand_profile(user_id, brand_name_to_create, **kwargs)
                return True
            return False

        updates, values = [], []
        json_fields = {'metadata', 'learned_signals', 'colors', 'fonts'}
        for key, val in kwargs.items():
            if val is None:
                continue
            if key in json_fields:
                if key in ('metadata', 'learned_signals'):
                    existing_val = json.loads(existing[key]) if existing[key] else {}
                    if isinstance(val, dict):
                        existing_val.update(val)
                    val = json.dumps(existing_val)
                else:
                    val = json.dumps(val)
            updates.append(f"{key} = ?")
            values.append(val)

        if not updates:
            return False
        updates.append("updated_at = ?")
        values.append(datetime.now())
        values.append(user_id)
        cursor.execute(f"UPDATE brand_profiles SET {', '.join(updates)} WHERE user_id = ?", values)
        return True

def merge_learned_signals(user_id: int, signals: Dict[str, Any]):
    """Merge new learned brand signals from agent interactions."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT learned_signals FROM brand_profiles WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return
        existing = json.loads(row[0]) if row[0] else {}
        existing.update(signals)
        cursor.execute(
            "UPDATE brand_profiles SET learned_signals=?, updated_at=? WHERE user_id=?",
            (json.dumps(existing), datetime.now(), user_id)
        )

def delete_brand_profile(user_id: int, brand_name: Optional[str] = None):
    """Delete brand profile for user, optionally scoped by brand_name."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if brand_name:
            cursor.execute("DELETE FROM brand_profiles WHERE user_id = ? AND brand_name = ?", (user_id, brand_name))
        else:
            cursor.execute("DELETE FROM brand_profiles WHERE user_id = ?", (user_id,))

def list_brand_profiles(user_id: int = None) -> List[Dict[str, Any]]:
    """Return all brand profiles. If user_id is given, that user's brands come first;
    brands from all users are always included so nothing is hidden due to user_id mismatch."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if user_id is not None:
            # Own brands first, then any others not yet in the list
            cursor.execute(
                "SELECT * FROM brand_profiles ORDER BY CASE WHEN user_id=? THEN 0 ELSE 1 END, updated_at DESC",
                (user_id,)
            )
        else:
            cursor.execute("SELECT * FROM brand_profiles ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        result = []
        for row in rows:
            profile = dict(row)
            for field in ('metadata', 'learned_signals'):
                if profile.get(field):
                    try:
                        profile[field] = json.loads(profile[field])
                    except Exception:
                        profile[field] = {}
            for field in ('colors', 'fonts'):
                if profile.get(field):
                    try:
                        profile[field] = json.loads(profile[field])
                    except Exception:
                        profile[field] = []
            result.append(profile)
        return result

def save_social_post(content_id: str, platform: str, post_url: str):
    """Save social media post for metrics tracking."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO social_posts (content_id, platform, post_id, post_url, posted_at)
        VALUES (?, ?, ?, ?, ?)
        """, (content_id, platform, content_id, post_url, datetime.now()))
        conn.commit()
        logger.info(f"Social post saved: {platform} - {post_url}")


def get_social_posts(platform: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return list of social posts, optionally filtered by platform."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if platform:
            cursor.execute("SELECT * FROM social_posts WHERE platform = ? ORDER BY posted_at DESC", (platform,))
        else:
            cursor.execute("SELECT * FROM social_posts ORDER BY posted_at DESC")
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({k: r[k] for k in r.keys()})
        return result


        return result


# ==================== CAMPAIGN OPERATIONS ====================

def create_campaign(campaign_id: str, user_id: int, name: str, start_date: str, end_date: str, 
                   budget_tier: str, strategy: str) -> str:
    """Create a new campaign."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO campaigns (id, user_id, name, status, start_date, end_date, budget_tier, strategy, created_at)
        VALUES (?, ?, ?, 'planning', ?, ?, ?, ?, ?)
        """, (campaign_id, user_id, name, start_date, end_date, budget_tier, strategy, datetime.now()))
        # Non-blocking sync to Neo4j
        try:
            sync_new_campaign({
                "id": campaign_id,
                "user_id": user_id,
                "name": name,
                "status": "planning",
                "start_date": start_date,
                "end_date": end_date,
                "budget_tier": budget_tier,
                "strategy": strategy,
                "created_at": datetime.now().isoformat()
            }, campaign_id)
        except Exception:
            logger.exception("Failed to sync campaign to Neo4j")
        return campaign_id

def get_campaign(campaign_id: str) -> Optional[Dict[str, Any]]:
    """Get campaign by ID."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def update_campaign_status(campaign_id: str, status: str):
    """Update campaign status."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE campaigns SET status = ? WHERE id = ?", (status, campaign_id))

def add_campaign_agenda_item(campaign_id: str, scheduled_time: str, action: str, metadata: Optional[Dict] = None):
    """Add an item to the campaign agenda."""
    metadata_json = json.dumps(metadata) if metadata else '{}'
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO campaign_agenda (campaign_id, scheduled_time, action, status, metadata, created_at)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """, (campaign_id, scheduled_time, action, metadata_json, datetime.now()))

def get_campaign_agenda(campaign_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get agenda items for a campaign."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("""
            SELECT * FROM campaign_agenda 
            WHERE campaign_id = ? AND status = ? 
            ORDER BY scheduled_time ASC
            """, (campaign_id, status))
        else:
            cursor.execute("""
            SELECT * FROM campaign_agenda 
            WHERE campaign_id = ? 
            ORDER BY scheduled_time ASC
            """, (campaign_id,))
        
        items = []
        for row in cursor.fetchall():
            item = dict(row)
            item['metadata'] = json.loads(item['metadata']) if item['metadata'] else {}
            items.append(item)
        return items

def get_pending_agenda_items(limit: int = 10) -> List[Dict[str, Any]]:
    """Get pending agenda items across all active campaigns that are due."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Join with campaigns to ensure we only get items for active campaigns
        cursor.execute("""
        SELECT ca.*, c.user_id 
        FROM campaign_agenda ca
        JOIN campaigns c ON ca.campaign_id = c.id
        WHERE ca.status = 'pending' 
        AND c.status = 'active'
        AND ca.scheduled_time <= datetime('now')
        ORDER BY ca.scheduled_time ASC
        LIMIT ?
        """, (limit,))
        
        items = []
        for row in cursor.fetchall():
            item = dict(row)
            item['metadata'] = json.loads(item['metadata']) if item['metadata'] else {}
            items.append(item)
        return items

def update_agenda_item_status(item_id: int, status: str, content_id: Optional[str] = None):
    """Update agenda item status and optionally link generated content."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if content_id:
            cursor.execute("""
            UPDATE campaign_agenda 
            SET status = ?, content_id = ? 
            WHERE id = ?
            """, (status, content_id, item_id))
        else:
            cursor.execute("""
            UPDATE campaign_agenda 
            SET status = ? 
            WHERE id = ?
            """, (status, item_id))

def delete_future_agenda_items(campaign_id: str):
    """Delete all pending future agenda items for a campaign (used for pivoting)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        DELETE FROM campaign_agenda 
        WHERE campaign_id = ? AND status = 'pending'
        """, (campaign_id,))


def get_reddit_posts_grouped() -> Dict[str, int]:
    """Return a mapping of subreddit -> number of saved posts in that subreddit.
    This inspects social_posts rows with platform='reddit' and parses subreddit from the post_url.
    """
    import re
    posts = get_social_posts(platform="reddit")
    counts: Dict[str, int] = {}
    pattern = re.compile(r"reddit\.com/r/([^/]+)/comments", re.IGNORECASE)
    for p in posts:
        url = p.get("post_url") or ""
        m = pattern.search(url)
        if m:
            subreddit = m.group(1).lower()
        else:
            subreddit = "unknown"
        counts[subreddit] = counts.get(subreddit, 0) + 1
    return counts
# ==================== RL OPERATIONS ====================

def save_rl_experience(state_vector: str, action_taken: str, reward: float, next_state_vector: Optional[str] = None):
    """Save RL experience for training."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO rl_state (state_vector, action_taken, reward, next_state_vector, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """, (state_vector, action_taken, reward, next_state_vector, datetime.now()))

def get_q_value(state_hash: str, action: str) -> float:
    """Get Q-value for state-action pair."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT q_value FROM q_table WHERE state_hash = ? AND action = ?", (state_hash, action))
        row = cursor.fetchone()
        return row[0] if row else 0.0

def update_q_value(state_hash: str, action: str, q_value: float):
    """Update Q-value for state-action pair."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO q_table (state_hash, action, q_value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(state_hash, action) DO UPDATE SET
        q_value = excluded.q_value,
        updated_at = excluded.updated_at
        """, (state_hash, action, q_value, datetime.now()))

def get_all_q_values(state_hash: str) -> Dict[str, float]:
    """Get all Q-values for a given state."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT action, q_value FROM q_table WHERE state_hash = ?", (state_hash,))
        return {row[0]: row[1] for row in cursor.fetchall()}

# ==================== PROMPT VERSIONS ====================

def save_prompt_version(agent_name: str, context_type: str, prompt_text: str,
                        langsmith_run_id: Optional[str] = None) -> str:
    import uuid as _uuid
    version_id = str(_uuid.uuid4())
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO prompt_versions (id, agent_name, context_type, prompt_text, langsmith_run_id, created_at)
        VALUES (?,?,?,?,?,?)
        """, (version_id, agent_name, context_type, prompt_text, langsmith_run_id, datetime.now()))
    return version_id

def update_prompt_score(version_id: str, score: float):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE prompt_versions SET performance_score=?, use_count=use_count+1, updated_at=?
        WHERE id=?
        """, (score, datetime.now(), version_id))

def get_best_prompt(agent_name: str, context_type: str) -> Optional[Dict[str, Any]]:
    """Return highest-scoring prompt for agent+context, or None if none scored yet."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM prompt_versions
        WHERE agent_name=? AND context_type=? AND performance_score IS NOT NULL
        ORDER BY performance_score DESC LIMIT 1
        """, (agent_name, context_type))
        row = cursor.fetchone()
        return dict(row) if row else None


# ==================== CRITIC LOGS ====================

def save_critic_log(content_id: str, session_id: Optional[str],
                    intent_score: float, brand_score: float, quality_score: float,
                    overall_score: float, critique_text: str, passed: bool,
                    langsmith_run_id: Optional[str] = None) -> int:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO critic_logs
            (content_id, session_id, intent_score, brand_score, quality_score,
             overall_score, critique_text, passed, langsmith_run_id, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (content_id, session_id, intent_score, brand_score, quality_score,
              overall_score, critique_text, 1 if passed else 0, langsmith_run_id, datetime.now()))
        return cursor.lastrowid

def update_critic_decision(content_id: str, decision: str):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE critic_logs SET user_decision=? WHERE content_id=? ORDER BY created_at DESC LIMIT 1",
            (decision, content_id)
        )

def get_critic_log(content_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM critic_logs WHERE content_id=? ORDER BY created_at DESC LIMIT 1", (content_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_recent_critic_logs(limit: int = 100) -> list:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT cl.id, cl.content_id, cl.session_id,
               cl.intent_score, cl.brand_score, cl.quality_score, cl.overall_score,
               cl.critique_text, cl.passed, cl.user_decision, cl.created_at,
               gc.type AS content_type,
               json_extract(gc.metadata, '$.brand_name') AS brand_name,
               gc.content
        FROM critic_logs cl
        LEFT JOIN generated_content gc ON gc.id = cl.content_id
        ORDER BY cl.created_at DESC
        LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            # Extract first 200 chars of actual content text for preview
            try:
                content_obj = json.loads(d.pop('content') or '{}')
                d['content_preview'] = list(content_obj.values())[0][:200] if content_obj else ''
            except Exception:
                d['content_preview'] = ''
            results.append(d)
        return results


# ==================== CAMPAIGN SCHEDULES ====================

def create_campaign_schedule(schedule_id: str, user_id: int, name: str, platform: str,
                              content_template: str, trigger_type: str,
                              run_at: Optional[str] = None, cron_expr: Optional[str] = None,
                              next_run: Optional[str] = None, metadata: Optional[Dict] = None) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO campaign_schedules
            (id, user_id, name, platform, content_template, trigger_type,
             run_at, cron_expr, next_run, metadata, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (schedule_id, user_id, name, platform, content_template, trigger_type,
              run_at, cron_expr, next_run, json.dumps(metadata or {}), datetime.now()))
    return schedule_id

def get_campaign_schedules(user_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if status:
            cursor.execute("SELECT * FROM campaign_schedules WHERE user_id=? AND status=? ORDER BY created_at DESC", (user_id, status))
        else:
            cursor.execute("SELECT * FROM campaign_schedules WHERE user_id=? ORDER BY created_at DESC", (user_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r['metadata'] = json.loads(r['metadata']) if r.get('metadata') else {}
            result.append(r)
        return result

def get_all_active_schedules() -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM campaign_schedules WHERE status='active'")
        rows = cursor.fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r['metadata'] = json.loads(r['metadata']) if r.get('metadata') else {}
            result.append(r)
        return result

def update_schedule_after_run(schedule_id: str, next_run: Optional[str] = None):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE campaign_schedules SET last_run=?, next_run=?, run_count=run_count+1 WHERE id=?
        """, (datetime.now().isoformat(), next_run, schedule_id))

def cancel_campaign_schedule(schedule_id: str, user_id: int):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE campaign_schedules SET status='cancelled' WHERE id=? AND user_id=?", (schedule_id, user_id))


# ==================== RESEARCH CACHE ====================

def get_research_cache(domain: str, depth_level: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM research_cache
        WHERE domain=? AND depth_level=? AND expires_at > datetime('now')
        """, (domain, depth_level))
        row = cursor.fetchone()
        if row:
            r = dict(row)
            r['result_json'] = json.loads(r['result_json'])
            return r
        return None

def save_research_cache(domain: str, depth_level: str, result: Dict[str, Any], ttl_hours: int = 72):
    from datetime import timedelta
    expires_at = (datetime.now() + timedelta(hours=ttl_hours)).isoformat()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO research_cache (domain, depth_level, result_json, created_at, expires_at)
        VALUES (?,?,?,?,?)
        ON CONFLICT(domain, depth_level) DO UPDATE SET
            result_json=excluded.result_json,
            created_at=excluded.created_at,
            expires_at=excluded.expires_at
        """, (domain, depth_level, json.dumps(result), datetime.now().isoformat(), expires_at))


# ==================== HITL EVENTS ====================

def create_hitl_event(event_id: str, session_id: str, user_id: int,
                      event_type: str, payload: Dict[str, Any]) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO hitl_events (id, session_id, user_id, event_type, payload, created_at)
        VALUES (?,?,?,?,?,?)
        """, (event_id, session_id, user_id, event_type, json.dumps(payload), datetime.now()))
    return event_id

def resolve_hitl_event(event_id: str, response: Dict[str, Any]):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE hitl_events SET status='responded', response=?, responded_at=? WHERE id=?
        """, (json.dumps(response), datetime.now(), event_id))

def get_hitl_event(event_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hitl_events WHERE id=?", (event_id,))
        row = cursor.fetchone()
        if row:
            r = dict(row)
            r['payload'] = json.loads(r['payload']) if r.get('payload') else {}
            r['response'] = json.loads(r['response']) if r.get('response') else None
            return r
        return None

def get_pending_hitl_events(session_id: str) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hitl_events WHERE session_id=? AND status='pending' ORDER BY created_at ASC", (session_id,))
        rows = cursor.fetchall()
        result = []
        for row in rows:
            r = dict(row)
            r['payload'] = json.loads(r['payload']) if r.get('payload') else {}
            result.append(r)
        return result


# ==================== WORKFLOW RUNS ====================

def create_workflow_run(run_id: str, session_id: str, user_id: int, workflow_name: str,
                        agent_sequence: List[str], agent_settings: Dict[str, Any],
                        langsmith_run_id: Optional[str] = None) -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO workflow_runs
            (id, session_id, user_id, workflow_name, agent_sequence, agent_settings, langsmith_run_id, started_at)
        VALUES (?,?,?,?,?,?,?,?)
        """, (run_id, session_id, user_id, workflow_name,
              json.dumps(agent_sequence), json.dumps(agent_settings), langsmith_run_id, datetime.now()))
    return run_id

def update_workflow_run(run_id: str, status: str, current_step: Optional[int] = None,
                        steps_output: Optional[Dict] = None, completed: bool = False):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        updates, values = ["status=?"], [status]
        if current_step is not None:
            updates.append("current_step=?"); values.append(current_step)
        if steps_output is not None:
            updates.append("steps_output=?"); values.append(json.dumps(steps_output))
        if completed:
            updates.append("completed_at=?"); values.append(datetime.now())
        values.append(run_id)
        cursor.execute(f"UPDATE workflow_runs SET {', '.join(updates)} WHERE id=?", values)

def get_workflow_run(run_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workflow_runs WHERE id=?", (run_id,))
        row = cursor.fetchone()
        if row:
            r = dict(row)
            for f in ('agent_sequence', 'agent_settings', 'steps_output'):
                r[f] = json.loads(r[f]) if r.get(f) else ([] if f == 'agent_sequence' else {})
            return r
        return None


# Initialize database on module import
try:
    initialize_database()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")

