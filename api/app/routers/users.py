# api/app/routers/users.py
from fastapi import APIRouter

router = APIRouter(prefix="/admin/users", tags=["Admin users"])
