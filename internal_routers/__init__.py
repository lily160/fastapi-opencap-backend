from fastapi import APIRouter
from .auth import router as auth_router
from .upload import router as upload_router
from .task import router as task_router
from .download import router as download_router
from .admin import router as admin_router

api_router = APIRouter()
api_router.include_router(auth_router, prefix="/auth", tags=["用户鉴权模块"])
api_router.include_router(upload_router, prefix="/upload", tags=["文件上传模块"])
api_router.include_router(task_router, prefix="/tasks", tags=["用户任务模块"])
api_router.include_router(download_router, prefix="/download", tags=["结果下载模块"]) # 【修改：修复原文截断注释】
api_router.include_router(admin_router, prefix="/admin", tags=["管理员模块"])