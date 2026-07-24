import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 1. 数据库配置与模型导入 (极度重要：必须引入 models 才能让底层的 create_all 扫描到表)
from database.db import engine, Base
from database.models import * # 2. 导入配置和路径常量
from config.settings import (
    BASE_STORAGE, UPLOAD_DIR, RESULT_DIR,
    METADATA_DIR, LOG_DIR, PROJECT_NAME, PROJECT_VERSION
)

# 3. 导入业务路由、内部算法路由与定时任务模块
from routers import api_router
from core.task_poller import start_scheduler

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