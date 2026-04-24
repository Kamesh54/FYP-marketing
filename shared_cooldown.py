"""
Shared global rate-limit cooldown tracker for Groq API.
All agents must check this before attempting Groq calls.
Prevents repeated 429 hammer-fest when token quota exhausted.
"""
import re
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional

# Global lock for thread-safe cooldown updates
_cooldown_lock = threading.Lock()

# Global cooldown dict: {model_name: datetime_when_available}
_MODEL_COOLDOWN_UNTIL: Dict[str, datetime] = {}


def is_model_on_cooldown(model_name: str) -> bool:
    """Check if model is currently on cooldown."""
    with _cooldown_lock:
        if model_name not in _MODEL_COOLDOWN_UNTIL:
            return False
        
        now = datetime.utcnow()
        cooldown_until = _MODEL_COOLDOWN_UNTIL[model_name]
        
        # Cooldown expired, clean up
        if now >= cooldown_until:
            del _MODEL_COOLDOWN_UNTIL[model_name]
            return False
        
        return True


def get_cooldown_remaining(model_name: str) -> Optional[float]:
    """Get remaining cooldown in seconds, or None if no cooldown."""
    with _cooldown_lock:
        if model_name not in _MODEL_COOLDOWN_UNTIL:
            return None
        
        now = datetime.utcnow()
        cooldown_until = _MODEL_COOLDOWN_UNTIL[model_name]
        
        remaining = (cooldown_until - now).total_seconds()
        if remaining <= 0:
            del _MODEL_COOLDOWN_UNTIL[model_name]
            return None
        
        return remaining


def set_cooldown(model_name: str, retry_after_seconds: float) -> None:
    """Set cooldown for model based on retry_after window."""
    with _cooldown_lock:
        cooldown_until = datetime.utcnow() + timedelta(seconds=retry_after_seconds)
        _MODEL_COOLDOWN_UNTIL[model_name] = cooldown_until


def parse_retry_after_seconds(error_message: str) -> Optional[float]:
    """Parse 'Please try again in X' from Groq 429 error message."""
    # Pattern: "Please try again in 3m37.728s" or "Please try again in 22m11.424s"
    match = re.search(r'Please try again in (\d+)m([\d.]+)s', error_message)
    if match:
        minutes = int(match.group(1))
        seconds = float(match.group(2))
        total_seconds = minutes * 60 + seconds
        return total_seconds
    
    # Fallback: pattern "Please try again in 10s"
    match = re.search(r'Please try again in ([\d.]+)s', error_message)
    if match:
        return float(match.group(1))
    
    return None


def should_skip_model(model_name: str) -> tuple[bool, Optional[float]]:
    """
    Check if model should be skipped due to cooldown.
    Returns: (should_skip: bool, remaining_seconds: float or None)
    """
    remaining = get_cooldown_remaining(model_name)
    should_skip = remaining is not None
    return should_skip, remaining


# Convenience function for Groq error handling
def handle_groq_429(model_name: str, error_dict: dict) -> None:
    """
    Extract retry_after from Groq 429 error and update global cooldown.
    
    Args:
        model_name: Name of Groq model that hit 429
        error_dict: Full error dict from Groq API (contains 'message' with retry time)
    """
    error_msg = error_dict.get('error', {}).get('message', '')
    retry_after = parse_retry_after_seconds(error_msg)
    
    if retry_after:
        set_cooldown(model_name, retry_after)
