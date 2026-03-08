"""
Social Media Metrics Collector
Fetches engagement metrics from Twitter and Instagram APIs
"""
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import tweepy
from instagrapi import Client as InstaClient
from dotenv import load_dotenv
from database import save_social_metrics, get_db_connection

load_dotenv()
logger = logging.getLogger(__name__)

# API Credentials
TWITTER_API_KEY = os.getenv("TWITTER_API_KEY")
TWITTER_API_SECRET = os.getenv("TWITTER_API_SECRET")
TWITTER_ACCESS_TOKEN = os.getenv("TWITTER_ACCESS_TOKEN")
TWITTER_ACCESS_TOKEN_SECRET = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

class MetricsCollector:
    """Collects metrics from social media platforms."""
    
    def __init__(self):
        self.twitter_client = None
        self.twitter_api_v1 = None
        self.instagram_client = None
        self._initialize_clients()
    
    def _initialize_clients(self):
        """Initialize API clients."""
        # Twitter client
        try:
            if all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_TOKEN_SECRET]):
                auth = tweepy.OAuth1UserHandler(
                    TWITTER_API_KEY,
                    TWITTER_API_SECRET,
                    TWITTER_ACCESS_TOKEN,
                    TWITTER_ACCESS_TOKEN_SECRET
                )
                self.twitter_api_v1 = tweepy.API(auth)
                self.twitter_client = tweepy.Client(
                    consumer_key=TWITTER_API_KEY,
                    consumer_secret=TWITTER_API_SECRET,
                    access_token=TWITTER_ACCESS_TOKEN,
                    access_token_secret=TWITTER_ACCESS_TOKEN_SECRET
                )
                logger.info("Twitter client initialized")
            else:
                logger.warning("Twitter credentials not configured")
        except Exception as e:
            logger.error(f"Failed to initialize Twitter client: {e}")
        
        # Instagram client
        try:
            if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
                self.instagram_client = InstaClient()
                if os.path.exists("instagram.json"):
                    self.instagram_client.load_settings("instagram.json")
                self.instagram_client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                logger.info("Instagram client initialized")
            else:
                logger.warning("Instagram credentials not configured")
        except Exception as e:
            logger.error(f"Failed to initialize Instagram client: {e}")
    
    def fetch_twitter_metrics(self, tweet_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch metrics for a specific tweet.
        
        Note: Requires Twitter API v2 Elevated access for full metrics.
        Free tier only provides basic public metrics for own tweets.
        
        Returns:
            {
                "likes": int,
                "retweets": int,
                "replies": int,
                "impressions": int (organic + promoted),
                "engagement_rate": float
            }
        """
        if not self.twitter_client:
            logger.warning("Twitter client not available")
            return None
        
        try:
            # Try to get tweet with full metrics (requires elevated access)
            try:
                tweet = self.twitter_client.get_tweet(
                    tweet_id,
                    tweet_fields=["public_metrics", "non_public_metrics", "organic_metrics"],
                    expansions=["author_id"]
                )
            except Exception as api_error:
                # If elevated access fails, try basic public metrics only
                if "401" in str(api_error) or "403" in str(api_error):
                    logger.warning(f"Elevated access not available for tweet {tweet_id}, trying basic metrics")
                    tweet = self.twitter_client.get_tweet(
                        tweet_id,
                        tweet_fields=["public_metrics"]
                    )
                else:
                    raise api_error
            
            if not tweet or not tweet.data:
                logger.warning(f"Tweet {tweet_id} not found or not accessible")
                return None
            
            metrics = tweet.data.public_metrics
            
            # Calculate engagement
            likes = metrics.get("like_count", 0)
            retweets = metrics.get("retweet_count", 0)
            replies = metrics.get("reply_count", 0)
            
            # Impressions require elevated access, estimate if not available
            impressions = metrics.get("impression_count", None)
            if impressions is None:
                # Estimate impressions based on engagement (rough heuristic)
                total_engagement = likes + retweets + replies
                impressions = max(total_engagement * 20, 100)  # Assume ~5% engagement rate
                logger.info(f"Estimated impressions for tweet {tweet_id}: {impressions}")
            
            engagement_rate = ((likes + retweets + replies) / impressions) * 100 if impressions > 0 else 0
            
            return {
                "likes": likes,
                "retweets": retweets,
                "replies": replies,
                "impressions": impressions,
                "engagement_rate": round(engagement_rate, 2)
            }
        
        except Exception as e:
            logger.error(f"Error fetching Twitter metrics for {tweet_id}: {e}")
            # If 401, provide helpful message
            if "401" in str(e):
                logger.error("Twitter API returned 401 Unauthorized. This likely means:")
                logger.error("  1. Twitter API v2 Elevated access is required for tweet metrics")
                logger.error("  2. Your Bearer Token may not have the required permissions")
                logger.error("  3. You can only access metrics for your own tweets with Basic access")
                logger.error("  Apply for Elevated access at: https://developer.twitter.com/en/portal/products/elevated")
            return None
    
    def fetch_instagram_metrics(self, media_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch metrics for an Instagram post.
        
        Args:
            media_id: Instagram shortcode (e.g., "ABC123xyz") or numeric media_pk
        
        Returns:
            {
                "likes": int,
                "comments": int,
                "reach": int,
                "impressions": int,
                "engagement_rate": float
            }
        """
        if not self.instagram_client:
            logger.warning("Instagram client not available")
            return None
        
        try:
            # Convert shortcode to media_pk if needed
            # If media_id contains letters, it's a shortcode and needs conversion
            if not media_id.isdigit():
                try:
                    media_pk = self.instagram_client.media_pk_from_code(media_id)
                    logger.info(f"Converted Instagram shortcode {media_id} to media_pk {media_pk}")
                except Exception as e:
                    logger.error(f"Failed to convert shortcode {media_id} to media_pk: {e}")
                    return None
            else:
                media_pk = media_id
            
            # Get media insights using numeric media_pk
            media_info = self.instagram_client.media_info(media_pk)
            
            likes = media_info.like_count or 0
            comments = media_info.comment_count or 0
            
            # Note: Reach and impressions require Instagram Business account and Graph API
            # Using instagrapi, these might not be available
            reach = 0
            impressions = 0
            
            # Try to get insights if available (Business accounts only)
            try:
                # This requires Business account
                insights = self.instagram_client.insights_media(media_pk)
                if insights:
                    reach = insights.get("reach", 0)
                    impressions = insights.get("impressions", 0)
            except Exception:
                # Fallback: estimate impressions from engagement
                impressions = max(likes + comments * 2, 100)  # Rough estimate
                reach = int(impressions * 0.8)
            
            engagement_rate = ((likes + comments) / impressions) * 100 if impressions > 0 else 0
            
            return {
                "likes": likes,
                "comments": comments,
                "reach": reach,
                "impressions": impressions,
                "engagement_rate": round(engagement_rate, 2)
            }
        
        except Exception as e:
            logger.error(f"Error fetching Instagram metrics for {media_id}: {e}")
            return None
    
    def collect_and_save_metrics(self, content_id: str, platform: str, post_id: str):
        """
        Collect metrics and save to database.
        
        Args:
            content_id: Internal content ID
            platform: "twitter" or "instagram"
            post_id: Platform-specific post ID
        """
        metrics = None
        
        if platform == "twitter":
            metrics = self.fetch_twitter_metrics(post_id)
        elif platform == "instagram":
            metrics = self.fetch_instagram_metrics(post_id)
        else:
            logger.error(f"Unsupported platform: {platform}")
            return
        
        if not metrics:
            logger.warning(f"Could not fetch metrics for {platform} post {post_id}")
            return
        
        # Save to database
        try:
            save_social_metrics(
                content_id=content_id,
                platform=platform,
                likes=metrics.get("likes", 0),
                comments=metrics.get("comments", metrics.get("replies", 0)),
                shares=metrics.get("retweets", 0),
                impressions=metrics.get("impressions", 0),
                reach=metrics.get("reach", 0)
            )
            logger.info(f"Saved metrics for {platform} post {post_id}: {metrics}")
        except Exception as e:
            logger.error(f"Error saving metrics: {e}")
    
    def collect_all_recent_metrics(self, days: int = 7):
        """
        Collect metrics for all posts from the last N days from social_posts table.
        """
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Get recent social posts
                cursor.execute("""
                SELECT sp.content_id, sp.platform, sp.post_url, sp.posted_at
                FROM social_posts sp
                WHERE sp.posted_at >= datetime('now', '-' || ? || ' days')
                ORDER BY sp.posted_at DESC
                """, (days,))
                
                posts = cursor.fetchall()
                
                logger.info(f"Collecting metrics for {len(posts)} posts...")
                
                for post in posts:
                    content_id = post[0]
                    platform = post[1]
                    post_url = post[2]
                    
                    try:
                        # Extract post ID from URL
                        post_id = self._extract_post_id_from_url(platform, post_url)
                        
                        if post_id:
                            logger.info(f"Fetching metrics for {platform} post: {post_id}")
                            self.collect_and_save_metrics(content_id, platform, post_id)
                        else:
                            logger.warning(f"Could not extract post ID from URL: {post_url}")
                    
                    except Exception as e:
                        logger.error(f"Error processing post {content_id}: {e}")
                
                logger.info("Metrics collection complete")
        
        except Exception as e:
            logger.error(f"Error in collect_all_recent_metrics: {e}")
    
    def _extract_post_id_from_url(self, platform: str, url: str) -> Optional[str]:
        """
        Extract post ID from social media URL.
        
        Examples:
            Twitter: https://twitter.com/user/status/1234567890 -> 1234567890
            Instagram: https://www.instagram.com/p/ABC123xyz/ -> ABC123xyz
        """
        if not url:
            return None
        
        try:
            if platform == "twitter":
                # Extract from: https://twitter.com/user/status/1234567890
                if "/status/" in url:
                    return url.split("/status/")[1].split("?")[0].strip("/")
            
            elif platform == "instagram":
                # Extract from: https://www.instagram.com/p/ABC123xyz/
                if "/p/" in url:
                    return url.split("/p/")[1].split("?")[0].strip("/")
            
            return None
        
        except Exception as e:
            logger.error(f"Error extracting post ID from {url}: {e}")
            return None

def get_aggregated_metrics(user_id: Optional[int] = None, days: int = 30) -> Dict[str, Any]:
    """
    Get aggregated metrics for dashboard display.
    
    Returns:
        {
            "total_posts": int,
            "total_engagement": int,
            "average_engagement_rate": float,
            "total_reach": int,
            "total_impressions": int,
            "by_platform": {
                "twitter": {...},
                "instagram": {...}
            },
            "top_posts": [...]
        }
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Base query
            query = """
            SELECT 
                sm.platform,
                COUNT(DISTINCT sm.content_id) as post_count,
                SUM(sm.likes + sm.comments + sm.shares) as total_engagement,
                AVG(sm.engagement_rate) as avg_engagement_rate,
                SUM(sm.reach) as total_reach,
                SUM(sm.impressions) as total_impressions
            FROM social_metrics sm
            JOIN generated_content gc ON sm.content_id = gc.id
            JOIN sessions s ON gc.session_id = s.id
            WHERE sm.timestamp >= datetime('now', '-' || ? || ' days')
            """
            params = [days]
            
            if user_id:
                query += " AND s.user_id = ?"
                params.append(user_id)
            
            query += " GROUP BY sm.platform"
            
            cursor.execute(query, params)
            platform_metrics = cursor.fetchall()
            
            # Aggregate totals
            total_posts = sum(row[1] for row in platform_metrics)
            total_engagement = sum(row[2] for row in platform_metrics)
            avg_engagement = sum(row[3] for row in platform_metrics) / len(platform_metrics) if platform_metrics else 0
            total_reach = sum(row[4] for row in platform_metrics)
            total_impressions = sum(row[5] for row in platform_metrics)
            
            # By platform breakdown
            by_platform = {}
            for row in platform_metrics:
                by_platform[row[0]] = {
                    "posts": row[1],
                    "engagement": row[2],
                    "avg_engagement_rate": round(row[3], 2),
                    "reach": row[4],
                    "impressions": row[5]
                }
            
            # Get top performing posts
            top_posts_query = """
            SELECT 
                sm.content_id,
                sm.platform,
                sm.engagement_rate,
                sm.likes + sm.comments + sm.shares as total_engagement,
                gc.metadata
            FROM social_metrics sm
            JOIN generated_content gc ON sm.content_id = gc.id
            JOIN sessions s ON gc.session_id = s.id
            WHERE sm.timestamp >= datetime('now', '-' || ? || ' days')
            """
            top_params = [days]
            
            if user_id:
                top_posts_query += " AND s.user_id = ?"
                top_params.append(user_id)
            
            top_posts_query += " ORDER BY sm.engagement_rate DESC LIMIT 10"
            
            cursor.execute(top_posts_query, top_params)
            top_posts = [
                {
                    "content_id": row[0],
                    "platform": row[1],
                    "engagement_rate": round(row[2], 2),
                    "total_engagement": row[3],
                    "preview": row[4][:100] if row[4] else ""
                }
                for row in cursor.fetchall()
            ]
            
            return {
                "total_posts": total_posts,
                "total_engagement": total_engagement,
                "average_engagement_rate": round(avg_engagement, 2),
                "total_reach": total_reach,
                "total_impressions": total_impressions,
                "by_platform": by_platform,
                "top_posts": top_posts
            }
    
    except Exception as e:
        logger.error(f"Error getting aggregated metrics: {e}")
        return {}

# Background job function (can be called by scheduler)
def collect_metrics_job():
    """Background job to collect metrics periodically."""
    logger.info("Starting metrics collection job...")
    collector = MetricsCollector()
    collector.collect_all_recent_metrics(days=7)
    logger.info("Metrics collection job complete")

def collect_metrics_for_post(content_id: str):
    """
    Manually trigger metrics collection for a specific post.
    Useful for immediate feedback after posting.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get post details from social_posts table
            cursor.execute("""
            SELECT platform, post_url
            FROM social_posts
            WHERE content_id = ?
            """, (content_id,))
            
            posts = cursor.fetchall()
            
            if not posts:
                logger.warning(f"No social posts found for content_id: {content_id}")
                return
            
            collector = MetricsCollector()
            
            for post in posts:
                platform = post[0]
                post_url = post[1]
                
                # Extract post ID from URL
                post_id = collector._extract_post_id_from_url(platform, post_url)
                
                if post_id:
                    logger.info(f"Collecting metrics for {platform} post {post_id}")
                    collector.collect_and_save_metrics(content_id, platform, post_id)
                else:
                    logger.warning(f"Could not extract post ID from URL: {post_url}")
    
    except Exception as e:
        logger.error(f"Error collecting metrics for post {content_id}: {e}")

