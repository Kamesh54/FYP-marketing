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
    
    # Job 3: RL model training (runs daily at 2 AM)
    def rl_training_job():
        try:
            from rl_agent import train_from_historical_data
            logger.info("Starting RL training job...")
            train_from_historical_data(days=30)
            logger.info("RL training job complete")
        except Exception as e:
            logger.error(f"Error in RL training job: {e}")
    
    scheduler.add_job(
        rl_training_job,
        CronTrigger(hour=2, minute=0),
        id="rl_training",
        name="Train RL model from historical data",
        replace_existing=True
    )
    logger.info("Scheduled: RL training at 2:00 AM")
    
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

