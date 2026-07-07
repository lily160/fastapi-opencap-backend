import os
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from database.db import get_db
from core.security import get_current_user
from database.models.sys_task_result import TaskResult
from database.models.sys_task import Task
from core.file_security import safe_path_check
from config.constants import CODE_FORBIDDEN, CODE_NOT_FOUND
router = APIRouter()

def stream_file(file_path: str):
    """流式分块读取大文件"""
    with open(file_path, "rb") as f:
        while chunk := f.read(1024*1024):
            yield chunk

@router.get("/result/{file_id}")
def download_result(
    file_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """模块5.1 结果文件流式下载接口"""
    user_id = current_user.user_id
    # 1. 查询结果文件
    result = db.query(TaskResult).filter(TaskResult.result_id == file_id, TaskResult.is_deleted == 0).first()
    if not result:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="文件不存在")
    # 2. 关联任务，校验文件归属
    task = db.query(Task).filter(Task.task_id == result.task_id, Task.is_deleted == 0).first()
    if not task:
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="关联任务不存在")
    if task.user_id != user_id and current_user.role not in ["admin", "super_admin"]:
        raise HTTPException(status_code=CODE_FORBIDDEN, detail="无权限下载他人文件")
    # 3. 路径防穿越校验
    safe_path_check(result.file_path)
    if not os.path.exists(result.file_path):
        raise HTTPException(status_code=CODE_NOT_FOUND, detail="文件已丢失")
    # 4. 流式返回文件
    filename = os.path.basename(result.file_path)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        stream_file(result.file_path),
        headers=headers,
        media_type="application/octet-stream"
    )