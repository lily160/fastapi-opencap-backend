from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from database.db import get_db
from core.security import get_current_user
from core.file_security import save_upload_file
from database.models.sys_upload_file import UploadFile
from schemas.upload.upload_schema import VideoUploadResp
from config.constants import CODE_SUCCESS
router = APIRouter()

@router.post("/video", status_code=CODE_SUCCESS, response_model=VideoUploadResp)
def upload_video(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """模块2.1 视频文件上传接口"""
    user_id = current_user.user_id
    # 安全存储文件
    file_info = save_upload_file(file, user_id)
    # 写入数据库
    db_file = UploadFile(
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