"""
Authentication Module
JWT-based authentication with bcrypt password hashing
"""
import os
import jwt
import bcrypt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from functools import wraps
from fastapi import HTTPException, Header
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 7

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False

def generate_jwt(user_id: int, email: str) -> Dict[str, Any]:
    """Generate JWT token for user."""
    expiration = datetime.utcnow() + timedelta(days=JWT_EXPIRATION_DAYS)
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": expiration,
        "iat": datetime.utcnow()
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {
        "token": token,
        "expires_at": expiration.isoformat(),
        "user_id": user_id,
        "email": email
    }

def verify_jwt(token: str) -> Dict[str, Any]:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

def extract_token_from_header(authorization: Optional[str] = None) -> Optional[str]:
    """Extract token from Authorization header."""
    if not authorization:
        return None
    
    # Expected format: "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    return parts[1]

def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    Dependency to get current user from JWT token.
    Use in FastAPI endpoints: user = Depends(get_current_user)
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    token = extract_token_from_header(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    
    payload = verify_jwt(token)
    return payload

def require_auth(func):
    """
    Decorator to require authentication for a function.
    Extracts user_id from JWT token and passes it to the function.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Extract authorization header from kwargs
        authorization = kwargs.get('authorization')
        if not authorization:
            raise HTTPException(status_code=401, detail="Authorization required")
        
        token = extract_token_from_header(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid authorization format")
        
        payload = verify_jwt(token)
        kwargs['user_id'] = payload['user_id']
        kwargs['user_email'] = payload['email']
        
        return await func(*args, **kwargs)
    return wrapper

def validate_email(email: str) -> bool:
    """Basic email validation."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength.
    Returns (is_valid, message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    
    return True, "Password is strong"

