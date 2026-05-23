from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional
from backend.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    verify_mock_google_token
)
from backend.database import get_user_by_email, get_user_by_username, create_user, get_user_by_id

router = APIRouter(tags=["Authentication"])

class SignupRequest(BaseModel):
    username: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class GoogleLoginRequest(BaseModel):
    credential: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

@router.post("/signup", response_model=TokenResponse)
async def signup(req: SignupRequest):
    # Check if email exists
    if get_user_by_email(req.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    # Check if username exists
    if get_user_by_username(req.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Hash password and create user
    hashed = get_password_hash(req.password)
    user_id = create_user(username=req.username, email=req.email, hashed_password=hashed)
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user record"
        )
    
    user_dict = dict(user)
    user_dict.pop("hashed_password", None)
    
    # Generate token
    token = create_access_token(data={"sub": user_id, "email": req.email})
    return TokenResponse(access_token=token, user=user_dict)

@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest):
    user = get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    user_dict = dict(user)
    user_dict.pop("hashed_password", None)
    
    # Generate token
    token = create_access_token(data={"sub": user["id"], "email": req.email})
    return TokenResponse(access_token=token, user=user_dict)

@router.post("/google", response_model=TokenResponse)
async def google_login(req: GoogleLoginRequest):
    # Validate the mock google token
    user_dict = verify_mock_google_token(req.credential)
    
    # Generate session token
    token = create_access_token(data={"sub": user_dict["id"], "email": user_dict["email"]})
    return TokenResponse(access_token=token, user=user_dict)

@router.get("/me")
async def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return current_user
