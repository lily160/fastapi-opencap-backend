from enum import Enum

# 用户角色
class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

# 任务状态
class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"

# 性别枚举
SexEnum = ("male", "female", "other")

# 配置文件类型
ConfigTypeEnum = ("calib", "intrinsics")

# 结果文件类型【新增：对齐V1.6结果文件枚举】
ResultFileTypeEnum = ("mono_json", "trc_file", "scaled_model", "visualization_video")

# 【修改：修复原PERMISSION_LIST语法错误，标准数组字典格式】
PERMISSION_LIST = [
    {"code": "task:create", "name": "创建任务"},
    {"code": "task:read:self", "name": "查看个人任务"},
    {"code": "task:cancel:self", "name": "取消个人任务"},
    {"code": "task:rerun:self", "name": "重跑个人任务"},
    {"code": "task:read:admin", "name": "查看全量任务"},
    {"code": "task:force_cancel:admin", "name": "管理员强制取消任务"},
    {"code": "task:delete:admin", "name": "批量删除任务"},
    {"code": "user:manage", "name": "用户管理"},
    {"code": "permission:manage", "name": "权限配置管理"},
]

# 通用HTTP状态码
CODE_SUCCESS = 200
CODE_CREATE = 201
CODE_NO_CONTENT = 204
CODE_PARAM_ERR = 400
CODE_UNAUTH = 401
CODE_FORBIDDEN = 403
CODE_NOT_FOUND = 404
CODE_CONFLICT = 409
CODE_SERVER_ERR = 500

# 【新增：忘记密码相关常量注释】
FORGOT_CONTACT_EMAIL = "email"
FORGOT_CONTACT_PHONE = "phone"