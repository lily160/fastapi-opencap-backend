from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class TaskCreateReq(BaseModel):
    video_file_id: str = Field(..., min_length=32, max_length=64, description="视频文件ID")
    height_m: float = Field(..., ge=0.5, le=3.0, description="身高(米)")
    mass_kg: float = Field(..., ge=10.0, le=300.0, description="体重(千克)")
    sex: str = Field(..., pattern="^(male|female|other)$", description="性别")
    activity: str = Field(..., min_length=1, max_length=50, description="运动类型")
    calib_path: Optional[str] = Field(None, max_length=255, description="标定文件路径(仅管理员)")
    intrinsics_path: Optional[str] = Field(None, max_length=255, description="相机内参路径(仅管理员)")
    estimate_local_only: bool = Field(False, description="是否仅本地估计")
    rerun: bool = Field(False, description="是否重跑")
    metadata_info: Optional[Dict[str, Any]] = Field(None, alias="metadata", description="自定义扩展字段")

    class Config:
        # 允许使用 alias (前端传 metadata，后端用 metadata_info 接收，避免和系统关键字冲突)
        populate_by_name = True
