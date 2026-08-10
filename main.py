import os
import asyncio
from contextlib import suppress, asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 1. 数据库配置与模型导入
from database.db import engine, Base
from sqlalchemy.orm import Session
from config.settings import (
    BASE_STORAGE, UPLOAD_DIR, RESULT_DIR,
    METADATA_DIR, LOG_DIR, PROJECT_NAME, PROJECT_VERSION
)
from database.models import *  # 从第二段引入的全局模型，用于解开建表命令
from database.models import Permission

# 2. 导入业务路由、内部算法路由与定时任务模块
from routers import api_router
from core.task_poller import start_scheduler

# 3. Kafka 相关导入 (来自第二段)
from kafka.consumer import start_consumer, stop_consumer, consume
from kafka.producer import start_producer, stop_producer, send_message


# ==========================================
# 【保留】权限点自动同步逻辑 (原封不动)
# ==========================================
def sync_permissions_to_db():
    """在系统启动时，自动将预设的权限点同步到数据库"""
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

    with Session(engine) as db:
        for perm in preset_permissions:
            exists = db.query(Permission).filter(Permission.permission_code == perm["code"]).first()

            if not exists:
                new_perm = Permission(
                    permission_code=perm["code"],
                    permission_name=perm["name"],
                    description=perm["desc"]
                )
                db.add(new_perm)
        db.commit()
        print("✅ 系统权限点字典自动同步完成")


# ==========================================
# 基础设施初始化 (保持第一段的同步逻辑)
# ==========================================

# 自动创建本地文件存储的五大核心文件夹
init_folders = [BASE_STORAGE, UPLOAD_DIR, RESULT_DIR, METADATA_DIR, LOG_DIR]
for folder in init_folders:
    os.makedirs(folder, exist_ok=True)

# 自动扫描并创建 MySQL 数据库里的表
print("当前扫描到的表有:", Base.metadata.tables.keys())
Base.metadata.create_all(bind=engine)

# ==========================================
# 融合生命周期管理 (整合了 Startup 和 Kafka)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🌟 1. 执行原第一段 startup 中的同步逻辑
    sync_permissions_to_db()

    # 🌟 2. 启动第二段引入的 Kafka Producer 和 Consumer
    await start_producer()
    await start_consumer()
    consumer_task = asyncio.create_task(consume())

    yield  # 这里是 FastAPI 正常运行的时间段

    # 🌟 3. 应用关闭时的清理工作
    consumer_task.cancel()
    with suppress(asyncio.CancelledError):
        await consumer_task

    await stop_consumer()
    await stop_producer()

    # 使用同步引擎的安全释放方式
    engine.dispose()


# ==========================================
# FastAPI 实例与中间件配置
# ==========================================

# 注册 lifespan
app = FastAPI(title=PROJECT_NAME, version=PROJECT_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8080",  # 视前端本地开发端口而定，比如 8080, 3000 或 5173
        "https://reshoot-seventh-huskiness.ngrok-free.dev"  # 你刚刚生成的 ngrok 穿透公网地址
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# 路由挂载
app.include_router(api_router, prefix="/api/v1")


# ==========================================
# 根路由与测试接口
# ==========================================



@app.get("/")
def root():
    """保留自第一段的同步状态检查接口"""
    return {"msg": f"{PROJECT_NAME} 后端服务运行正常，接口文档请访问 /docs"}


if __name__ == "__main__":
    import uvicorn

    # 融合了两段代码的启动特点
    reload_enabled = os.getenv("UVICORN_RELOAD", "true").lower() == "true"
    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=reload_enabled)
