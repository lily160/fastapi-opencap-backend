import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 1. 数据库配置与模型导入 (极度重要：必须引入 models 才能让底层的 create_all 扫描到表)
from database.db import engine, Base
# 【新增】需要从 SQLAlchemy 导入 Session 用于独立管理数据库连接
from sqlalchemy.orm import Session
from config.settings import (
    BASE_STORAGE, UPLOAD_DIR, RESULT_DIR,
    METADATA_DIR, LOG_DIR, PROJECT_NAME, PROJECT_VERSION
)
from database.models import Permission

# 3. 导入业务路由、内部算法路由与定时任务模块
from routers import api_router
from core.task_poller import start_scheduler

# ==========================================
# 【新增】权限点自动同步逻辑
# ==========================================
def sync_permissions_to_db():
    """在系统启动时，自动将预设的权限点同步到数据库"""
    # 定义系统所有可用的权限点（匹配 Permission 模型的 name 和 description 要求）
    preset_permissions = [
        # ================= 任务模块 (Task) =================
        {"code": "task:create", "name": "创建任务", "desc": "允许用户创建全新的分析任务"},
        {"code": "task:read:self", "name": "查看个人任务", "desc": "仅能查看用户自己创建的任务"},
        {"code": "task:cancel:self", "name": "取消个人任务", "desc": "允许用户取消自己创建且处于排队或运行状态的任务"},
        {"code": "task:rerun:self", "name": "重跑个人任务", "desc": "允许用户使用原视频和参数重新运行自己创建的任务"},
        {"code": "task:read:admin", "name": "查看全部任务", "desc": "管理员查看系统中所有人的任务"},
        {"code": "task:force_cancel:admin", "name": "强制取消任务", "desc": "管理员强制中断或取消系统中任意用户的任务"},
        {"code": "task:delete:admin", "name": "批量删除任务", "desc": "管理员批量清理或删除系统中的任意任务数据"},

        # ================= 用户与权限模块 (User & RBAC) =================
        {"code": "user:read", "name": "查看用户列表", "desc": "管理员查看系统内全量用户列表及其基本信息"},
        {"code": "user:manage", "name": "用户管理", "desc": "管理系统用户的状态（如封禁/解封）"},
        {"code": "permission:manage", "name": "权限配置", "desc": "超级管理系统角色和特化权限点配置"},

        # ================= 系统配置模块 (System Config) =================
        {"code": "camera:read", "name": "查看相机配置", "desc": "允许查看系统中已上传的相机标定和内参配置文件"},
        {"code": "camera:manage", "name": "管理相机配置", "desc": "允许管理员上传、更新或删除相机配置文件"}
    ]

    # 利用 engine 开启一个临时的数据库会话
    with Session(engine) as db:
        for perm in preset_permissions:
            # 去数据库查一下这个权限代码是否已经录入过了
            exists = db.query(Permission).filter(Permission.permission_code == perm["code"]).first()
            if not exists:
                # 如果没查到，就把它存入数据库
                new_perm = Permission(
                    permission_code=perm["code"],
                    permission_name=perm["name"],
                    description=perm["desc"]
                )
                db.add(new_perm)
        db.commit()
        print("✅ 系统权限点字典自动同步完成")

# ==========================================
# 基础设施初始化
# ==========================================

# 自动创建本地文件存储的五大核心文件夹
init_folders = [BASE_STORAGE, UPLOAD_DIR, RESULT_DIR, METADATA_DIR, LOG_DIR]
for folder in init_folders:
    os.makedirs(folder, exist_ok=True)

# 自动扫描并创建 MySQL 数据库里的 10 张表
print("当前扫描到的表有:", Base.metadata.tables.keys())
Base.metadata.create_all(bind=engine)

# ==========================================
# FastAPI 实例与中间件配置
# ==========================================

app = FastAPI(title=PROJECT_NAME, version=PROJECT_VERSION)

# 跨域资源共享 (CORS) 配置，允许前端网页随意调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ==========================================
# 路由挂载 (接客入口)
# ==========================================

# 挂载对外公开的业务接口（用户、上传、任务等），统一加上 /api/v1 前缀
app.include_router(api_router, prefix="/api/v1")

# ==========================================
# 生命周期事件与根路由
# ==========================================

@app.on_event("startup")
async def startup_event():
    """项目启动时自动执行的逻辑"""
    # 自动同步权限字典到数据库
    sync_permissions_to_db()

    # 启动后台任务轮询监工
    # 【优化点】放在 startup 事件里启动，能确保异步事件循环 (Event Loop) 已经就绪
    start_scheduler()

@app.get("/")
def root():
    return {"msg": f"{PROJECT_NAME} 后端服务运行正常，接口文档请访问 /docs"}

if __name__ == "__main__":
    import uvicorn
    # reload=True 方便你在开发调试时修改代码自动重启
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)