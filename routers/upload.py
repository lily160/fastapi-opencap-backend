from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from database.db import get_db
from core.file_security import save_upload_file
from core.security import AuthContext, get_auth_context

# 给数据库模型加上 as DBUploadFile 进行重命名隔离
from database.models.sys_upload_file import UploadFile as DBUploadFile
from schemas.upload.upload_schema import VideoUploadResp
from config.constants import CODE_SUCCESS

router = APIRouter()


@router.post("/video", status_code=CODE_SUCCESS, response_model=VideoUploadResp)
def upload_video(
        file: UploadFile = File(...),  # ✅ 这里的 UploadFile 现在安全了，它指向 FastAPI内置类
        db: Session = Depends(get_db),
        auth_context: AuthContext = Depends(get_auth_context)
):
    """模块2.1 视频文件上传接口"""
    user_id = auth_context.user.user_id

    # 安全存储文件
    file_info = save_upload_file(file, user_id)

    # 【修改点 2】：下面实例化数据库对象时，使用别名 DBUploadFile
    db_file = DBUploadFile(
        file_id=file_info["file_id"],
        user_id=user_id,
        original_name=file_info["original_name"],
        storage_name=file_info["storage_name"],
        file_path=file_info["file_path"],
        file_size=file_info["file_size"],
        mime_type=file_info["mime_type"],
        file_type=file_info["file_type"],
        is_deleted=0
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    return VideoUploadResp(
        file_id=db_file.file_id,
        filename=db_file.original_name,
        size=db_file.file_size,
        mime_type=db_file.mime_type
    )
