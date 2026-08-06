import os
from fastapi import UploadFile, HTTPException
from config.settings import MAX_VIDEO_SIZE, VIDEO_ALLOW, UPLOAD_DIR
from utils.uuid_util import generate_uuid
# 视频MIME白名单
VIDEO_MIME_WHITE = {"video/mp4", "video/mov", "video/x-msvideo"}


def check_file_security(file: UploadFile):
    """多层安全校验：大小、后缀、MIME、内容头"""
    # 1. 文件大小校验
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > MAX_VIDEO_SIZE:
        raise HTTPException(status_code=400, detail=f"文件超过最大限制{MAX_VIDEO_SIZE//1024//1024}MB")
    # 2. 后缀名校验
    suffix = file.filename.split(".")[-1].lower()
    if suffix not in VIDEO_ALLOW:
        raise HTTPException(status_code=400, detail=f"仅支持视频格式：{VIDEO_ALLOW}")
    # 3. MIME类型校验
    if file.content_type not in VIDEO_MIME_WHITE:
        raise HTTPException(status_code=400, detail="文件真实类型非视频，禁止上传")
    return file_size, suffix


def save_upload_file(file: UploadFile, user_id: str) -> dict:
    """生成随机file_id，重命名存储，返回文件信息"""
    file_size, suffix = check_file_security(file)
    file_id = generate_uuid()
    storage_name = f"{file_id}.{suffix}"
    store_path = os.path.join(UPLOAD_DIR, storage_name)
    # 流式写入防内存溢出
    with open(store_path, "wb") as f:
        while chunk := file.file.read(1024*1024):
            f.write(chunk)
    return {
        "file_id": file_id,
        "original_name": file.filename,
        "storage_name": storage_name,
        "file_path": store_path,
        "file_size": file_size,
        "mime_type": file.content_type,
        "file_type": "video"
    }


def safe_path_check(target_path: str):
    """防止路径穿越攻击，校验文件路径在允许目录内"""
    from config.settings import RESULT_DIR, UPLOAD_DIR
    allow_dirs = [UPLOAD_DIR, RESULT_DIR]
    abs_target = os.path.abspath(target_path)
    in_allow = any(abs_target.startswith(os.path.abspath(d)) for d in allow_dirs)
    if not in_allow:
        raise HTTPException(status_code=400, detail="非法文件路径，禁止访问")


# 新增：管理员上传相机配置yaml文件
def save_config_file(file: UploadFile, admin_user_id: str, file_type: str) -> dict:
    """保存calib/intrinsics yaml配置文件，校验后缀，生成file_id"""
    import os
    from config.settings import UPLOAD_DIR
    from config.constants import CONFIG_ALLOW
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    suffix = file.filename.split(".")[-1].lower()
    if suffix not in CONFIG_ALLOW:
        raise HTTPException(status_code=400, detail="仅支持yaml/yml配置文件")
    file_id = generate_uuid()
    storage_name = f"{file_id}.{suffix}"
    store_path = os.path.join(UPLOAD_DIR, "config", storage_name)
    os.makedirs(os.path.join(UPLOAD_DIR, "config"), exist_ok=True)
    with open(store_path, "wb") as f:
        while chunk := file.read(1024*1024):
            f.write(chunk)
    return {
        "file_id": file_id,
        "original_name": file.filename,
        "storage_name": storage_name,
        "file_path": store_path,
        "file_size": file_size,
        "mime_type": "text/yaml",
        "file_type": "config"
    }
