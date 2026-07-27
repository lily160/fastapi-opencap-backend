from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# 分页通用
class PageResp(BaseModel):
    total: int
    page: int
    page_size: int

# 6.2 相机配置上传返回
class CameraConfigResp(BaseModel):
    config_id: str
    device_model: str
    file_type: str
    updated_at: str

# 6.3 配置列表项
class CameraConfigItem(BaseModel):
    config_id: str
    device_model: str
    file_type: str
    file_name: str
    uploaded_by_username: str
    updated_at: str

# 6.5 用户列表项
class AdminUserItem(BaseModel):
    user_id: str
    username: str
    role: str
    is_active: bool
    task_count: int
    created_at: str

# 6.6 用户状态修改
class UserStatusUpdate(BaseModel):
    is_active: bool

# 6.8 角色变更入参
class UserRoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|admin)$")

# 6.9 批量删除任务
class BatchDeleteTaskReq(BaseModel):
    task_ids: List[str] = Field(max_items=100)
    reason: Optional[str] = Field(None, max_length=200)
class BatchDeleteResp(BaseModel):
    deleted_count: int
    failed: List[Dict[str, str]]

# 6.11 角色权限配置
class RolePermissionReq(BaseModel):
    permissions: List[str]
# 6.12 用户权限覆盖
class UserPermissionOverrideReq(BaseModel):
    grant: List[str]
    revoke: List[str]