import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 1. 解开导入
from database.db import engine, Base
from database.models import * # 2. 解开建表命令
Base.metadata.create_all(bind=engine)

# 导入配置和路径常量
from config.settings import BASE_STORAGE, UPLOAD_DIR, RESULT_DIR, METADATA_DIR, LOG_DIR, PROJECT_NAME, PROJECT_VERSION
from routers import api_router

# --- 注意：以下模块在组员开发完毕前暂时注释，防止启动报错 ---
# from routers import api_router
# from internal_routers.algo import algo_router
# from database.db import engine, Base
# from core.task_poller import start_scheduler
# from database.models import sys_user, ...

# 初始化文件夹 (修复了原文档中的变量错误)
init_folders = [BASE_STORAGE, UPLOAD_DIR, RESULT_DIR, METADATA_DIR, LOG_DIR]
for folder in init_folders:
    os.makedirs(folder, exist_ok=True)

# 自动建表 (连接数据库时解开)
# Base.metadata.create_all(bind=engine)

# 启动定时轮询任务 (组员 B 开发完成后解开)
# start_scheduler()

app = FastAPI(title=PROJECT_NAME, version=PROJECT_VERSION)

# 跨域配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(api_router, prefix="/api/v1")
# app.include_router(algo_router)

@app.get("/")
def root():
    return {"msg": "服务正常，文档地址 /docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
