import os
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from backend.database import get_user_by_id, get_user_by_email, create_user

# Secret key details
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "skct-college-assistant-super-secret-key-987654321")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 Hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check if the plain password matches the hashed password."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Generate a bcrypt hash of the password."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a JWT token for the user session."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Retrieve the current logged-in user details from the JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not token:
        raise credentials_exception
        
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
        
    user_id_val = payload.get("sub")
    if user_id_val is None:
        raise credentials_exception
        
    try:
        user_id = int(user_id_val)
    except (ValueError, TypeError):
        user_id = user_id_val

    user = get_user_by_id(user_id)
    if user is None:
        raise credentials_exception
        
    # Convert Row or Dict to standard dict and exclude password
    user_dict = dict(user)
    user_dict.pop("hashed_password", None)
    return user_dict

def verify_mock_google_token(credential: str) -> Dict[str, Any]:
    """
    Validates a Google mock token. Since a full Google Client configuration
    requires server credentials and network requests, we mock this locally.
    Any email received is converted into a session token.
    """
    # For a real application, we would use: google.oauth2.id_token.verify_oauth2_token(credential, requests.Request(), CLIENT_ID)
    # Here we mock it by splitting or reading the payload
    # Let's assume the client passes user email/name as a JSON string or mock token
    try:
        # Check if the token format is a simulated payload: "mock_google_<email>_<name>"
        if credential.startswith("mock_google_"):
            parts = credential.split("_")
            email = parts[2]
            name = parts[3] if len(parts) > 3 else email.split("@")[0]
        else:
            # Fallback
            email = "googleuser@skct.edu.in"
            name = "Google User"
            
        # Check if the user exists in our DB, if not, create them
        user = get_user_by_email(email)
        if not user:
            # Create a mock hashed password
            dummy_password = get_password_hash(f"google-oauth-dummy-{email}")
            user_id = create_user(username=name.lower().replace(" ", "_"), email=email, hashed_password=dummy_password)
            user = get_user_by_id(user_id)
            
        user_dict = dict(user)
        user_dict.pop("hashed_password", None)
        return user_dict
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Google OAuth token payload: {exc}"
        )
