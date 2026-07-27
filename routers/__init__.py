from fastapi import APIRouter

from routers import auth, task, upload, download, admin

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(task.router, prefix="/task", tags=["task"])
api_router.include_router(download.router, prefix="/download", tags=["download"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])