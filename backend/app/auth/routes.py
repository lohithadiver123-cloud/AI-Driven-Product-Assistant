from fastapi import APIRouter, HTTPException, status
from ..auth import schemas
from .schemas import SignupRequest, LoginRequest, TokenResponse
from .utils import create_user, authenticate_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
async def signup(payload: SignupRequest):
    try:
        res = await create_user(payload.name, payload.email, payload.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"access_token": res["token"], "token_type": "bearer"}


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    res = await authenticate_user(payload.email, payload.password)
    if not res:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return {"access_token": res["token"], "token_type": "bearer"}
