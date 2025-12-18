from fastapi import APIRouter, HTTPException, Body
from app.services.telegram_service import telegram_service
from pydantic import BaseModel

router = APIRouter()

class PhoneRequest(BaseModel):
    phone: str

class LoginRequest(BaseModel):
    phone: str
    code: str
    phone_code_hash: str

class PasswordRequest(BaseModel):
    password: str

@router.get("/status")
async def get_auth_status():
    return await telegram_service.get_status()

@router.post("/request-code")
async def request_code(request: PhoneRequest):
    try:
        result = await telegram_service.send_code(request.phone)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login(request: LoginRequest):
    try:
        result = await telegram_service.sign_in(
            phone=request.phone,
            code=request.code,
            phone_code_hash=request.phone_code_hash
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/password")
async def login_password(request: PasswordRequest):
    try:
        result = await telegram_service.sign_in_password(request.password)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
