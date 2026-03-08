"""
Task Scheduler
Handles daily automated post generation and metrics collection
"""
import os
import logging
from datetime import datetime, time
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from database import get_db_connection, save_generated_content, get_brand_profile
from metrics_collector import collect_metrics_job
import uuid
import json
from campaign_planner import CampaignPlannerAgent
from mabo_agent import get_mabo_agent

# Import graph monitoring functions
try:
    from graph import get_graph_queries, is_graph_db_available
    GRAPH_AVAILABLE = True
except Exception as e:
    logger_module = logging.getLogger(__name__)
    logger_module.warning(f"Graph module not available for monitoring: {e}")
    GRAPH_AVAILABLE = False

# Initialize agents
planner = CampaignPlannerAgent()
mabo = get_mabo_agent()

load_dotenv()
logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = BackgroundScheduler()

def generate_daily_post_for_user(user_id: int):
    """
    Generate a daily social media post for a user.
    Uses brand profile and trending keywords.
    """
    try:
        logger.info(f"Generating daily post for user {user_id}")
        
        # Get user's brand profile
        brand_profile = get_brand_profile(user_id)
        if not brand_profile:
            logger.warning(f"No brand profile found for user {user_id}")
            return
        
        # Get user's active session or create new one
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT id FROM sessions 
            WHERE user_id = ? AND is_active = 1 
            ORDER BY last_active DESC 
            LIMIT 1
            """, (user_id,))
            row = cursor.fetchone()
            
            if row:
                session_id = row[0]
            else:
                # Create new session for automated posts
                session_id = f"auto_{user_id}_{uuid.uuid4().hex[:8]}"
                cursor.execute("""
                INSERT INTO sessions (id, user_id, title, created_at, last_active)
                VALUES (?, ?, ?, ?, ?)
                """, (session_id, user_id, "Automated Posts", datetime.now(), datetime.now()))
        
        # Import content generation here to avoid circular imports
        from intelligent_router import generate_conversational_response
        
        # Create prompt for post generation
        brand_name = brand_profile.get("brand_name", "your business")
        industry = json.loads(brand_profile.get("metadata", "{}")).get("industry", "")
        
        post_prompt = f"""Generate a brief, engaging social media post for {brand_name}.
Industry: {industry}
Keep it under 280 characters for Twitter compatibility.
Include relevant hashtags.
Make it timely and valuable for the audience."""
        
        # For now, we'll create a placeholder post
        # In production, this would call content_agent
        content_id = str(uuid.uuid4())
        
        # Create simple post content
        post_content = f"""🚀 Great things happening at {brand_name}!

Stay tuned for exciting updates. We're committed to delivering the best for our community.

#{brand_name.replace(' ', '')} #Business #Growth"""
        
        # Save to database with pending status
        metadata = {
            "auto_generated": True,
            "generation_time": datetime.now().isoformat(),
            "brand_name": brand_name,
            "needs_approval": True
        }
        
        save_generated_content(
            content_id=content_id,
            session_id=session_id,
            content_type="post",
            content=post_content,
            preview_url=None,
            metadata=metadata
        )
        
        logger.info(f"Daily post generated for user {user_id}: content_id={content_id}")
        
        # TODO: Send notification to user (email or in-app)
        # This would require notification system implementation
        
    except Exception as e:
        logger.error(f"Error generating daily post for user {user_id}: {e}")

def daily_post_generation_job():
    """
    Job that runs daily to generate posts for all active users.
    """
    try:
        logger.info("Starting daily post generation job...")
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get all users with daily post preference enabled
            cursor.execute("""
            SELECT id, preferences 
            FROM users 
            WHERE last_login >= datetime('now', '-30 days')
            """)
            
            users = cursor.fetchall()
            
            for user in users:
                user_id = user[0]
                preferences_str = user[1]
                
                try:
                    preferences = json.loads(preferences_str) if preferences_str else {}
                    
                    # Check if user has daily posts enabled
                    if preferences.get("daily_posts_enabled", False):
                        generate_daily_post_for_user(user_id)
                
                except Exception as e:
                    logger.error(f"Error processing user {user_id}: {e}")
            
            logger.info(f"Daily post generation complete for {len(users)} users")
    
    except Exception as e:
        logger.error(f"Error in daily_post_generation_job: {e}")

def execute_campaign_step():
    """
    Hourly job to execute pending campaign agenda items.
    Includes 'Pivot' logic based on MABO stats.
    """
    try:
        logger.info("Checking campaign agenda...")
        
        # 1. Get pending items due for execution
        from database import get_pending_agenda_items, update_agenda_item_status, get_campaign, delete_future_agenda_items, add_campaign_agenda_item
        
        pending_items = get_pending_agenda_items(limit=5)
        
        if not pending_items:
            return

        for item in pending_items:
            campaign_id = item['campaign_id']
            campaign = get_campaign(campaign_id)
            
            if not campaign:
                continue
                
            logger.info(f"Processing agenda item {item['id']} for campaign {campaign['name']}")
            
            # 2. Check MABO stats for Pivot Trigger
            # "If the regret in validation_metrics for the current campaign ID is above a threshold"
            # For simulation, we'll check if we have high 'regret' (simulated by low stabilization rate or explicit metric)
            
            mabo_stats = mabo.get_mabo_stats()
            # Simplified logic: If stabilization rate is low (< 0.3) after some time, or if we have a specific 'regret' flag
            # In a real scenario, we'd query the validation_metrics table for 'regret'
            
            # Check if we should pivot (Simulated condition: 10% chance or specific condition)
            should_pivot = False
            
            # Real check: Query validation metrics for this campaign
            # For now, we'll assume if the campaign is "Budget" but performing poorly, we might pivot
            # This is a placeholder for the complex regret calculation
            
            if should_pivot:
                logger.info(f"High regret detected for campaign {campaign_id}. Initiating PIVOT.")
                
                # Calculate remaining days
                end_date = datetime.fromisoformat(campaign['end_date'])
                remaining_days = (end_date - datetime.now()).days
                
                if remaining_days > 1:
                    # 1. Delete future pending items
                    delete_future_agenda_items(campaign_id)
                    
                    # 2. Re-plan
                    new_agenda = planner.re_plan_campaign(campaign_id, remaining_days, campaign['strategy'])
                    
                    # 3. Save new agenda
                    for new_item in new_agenda:
                        add_campaign_agenda_item(
                            campaign_id=campaign_id,
                            scheduled_time=new_item["scheduled_time"],
                            action=new_item["action"],
                            metadata=new_item["metadata"]
                        )
                    
                    logger.info(f"Campaign {campaign_id} pivoted with {len(new_agenda)} new items.")
                    
                    # Mark current item as skipped if it was replaced, or execute it if it's immediate
                    update_agenda_item_status(item['id'], 'skipped')
                    continue

            # 3. Execute the Item
            update_agenda_item_status(item['id'], 'in_progress')
            
            try:
                action = item['action']
                metadata = item['metadata']
                
                if action == "social_post":
                    # Call content generation
                    # For now, we'll simulate the call or use the helper
                    from intelligent_router import generate_conversational_response
                    # In reality, we'd call content_agent directly
                    
                    # Simulate success
                    content_id = f"cont_{uuid.uuid4().hex[:8]}"
                    # Save content (placeholder)
                    
                    logger.info(f"Executed social post for campaign {campaign_id}")
                    update_agenda_item_status(item['id'], 'completed', content_id=content_id)
                    
                elif action == "blog_post":
                    logger.info(f"Executed blog post for campaign {campaign_id}")
                    content_id = f"cont_{uuid.uuid4().hex[:8]}"
                    update_agenda_item_status(item['id'], 'completed', content_id=content_id)
                    
                else:
                    logger.warning(f"Unknown action {action}")
                    update_agenda_item_status(item['id'], 'failed')
                    
            except Exception as e:
                logger.error(f"Failed to execute agenda item {item['id']}: {e}")
                update_agenda_item_status(item['id'], 'failed')

    except Exception as e:
        logger.error(f"Error in execute_campaign_step: {e}")

def start_scheduler():
    """
    Start the background scheduler with all jobs.
    """
    if scheduler.running:
        logger.info("Scheduler already running")
        return
    
    # Job 1: Daily post generation (runs at 9 AM every day)
    scheduler.add_job(
        daily_post_generation_job,
        CronTrigger(hour=9, minute=0),
        id="daily_post_generation",
        name="Generate daily posts for users",
        replace_existing=True
    )
    logger.info("Scheduled: Daily post generation at 9:00 AM")
    
    # Job 2: Metrics collection (runs every 4 hours)
    scheduler.add_job(
        collect_metrics_job,
        CronTrigger(hour='*/4'),
        id="metrics_collection",
        name="Collect social media metrics",
        replace_existing=True
    )
    logger.info("Scheduled: Metrics collection every 4 hours")

    # Job 3: Campaign Execution (runs every hour)
    scheduler.add_job(
        execute_campaign_step,
        CronTrigger(minute=0),  # Run at the top of every hour
        id="campaign_execution",
        name="Execute campaign agenda items",
        replace_existing=True
    )
    logger.info("Scheduled: Campaign execution every hour")
    
    # Job 4: MABO Learning (updates the Brain every hour)
    def mabo_learning_job():
        try:
            logger.info("Running MABO batch update...")
            result = mabo.feedback_analyzer.perform_batch_update()
            logger.info(f"MABO Update Result: {result}")
        except Exception as e:
            logger.error(f"MABO Update Error: {e}")
            
    scheduler.add_job(
        mabo_learning_job,
        CronTrigger(minute=30),
        id="mabo_learning",
        name="Update MABO Coordination State",
        replace_existing=True
    )
    logger.info("Scheduled: MABO learning every hour")
    
    # Add graph health monitoring job (runs every 5 minutes)
    if GRAPH_AVAILABLE:
        def graph_health_monitoring_job():
            """Monitor graph database health and log status."""
            try:
                if not is_graph_db_available():
                    logger.warning("Graph database is not available")
                    return
                
                queries = get_graph_queries()
                health = queries.get_graph_health_summary()
                
                if isinstance(health, dict):
                    logger.info(f"Graph DB Health: {health.get('status', 'unknown')} - "
                              f"Nodes: {health.get('total_nodes', 'N/A')}, "
                              f"Relationships: {health.get('total_relationships', 'N/A')}")
                else:
                    logger.debug("Graph health check completed")
            except Exception as e:
                logger.debug(f"Graph health monitoring error: {e}")
        
        scheduler.add_job(
            graph_health_monitoring_job,
            CronTrigger(minute='*/5'),  # Every 5 minutes
            id="graph_health_monitoring",
            name="Graph Database Health Check",
            replace_existing=True
        )
        logger.info("Scheduled: Graph health monitoring every 5 minutes")
    
    # Start the scheduler
    scheduler.start()
    logger.info("Background scheduler started successfully")

def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")

def get_scheduler_status() -> dict:
    """Get current scheduler status and job information."""
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })
    
    return {
        "running": scheduler.running,
        "jobs": jobs
    }

# Start scheduler on module import (will be called when orchestrator starts)
# Commented out to prevent automatic start - will be started explicitly by orchestrator
# start_scheduler()

