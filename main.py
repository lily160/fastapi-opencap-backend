import os
import asyncio
from contextlib import suppress
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from kafka.consumer import start_consumer,stop_consumer,consume
from kafka.producer import start_producer, stop_producer, send_message
# 1. 解开导入
from database.db import engine, Base
from database.models import * # 2. 解开建表命令

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
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    # 启动 Producer
    await start_producer()

    # 启动 Consumer
    await start_consumer()

    # 创建后台消费任务
    consumer_task = asyncio.create_task(consume())

    yield

    # 应用关闭时取消后台任务
    consumer_task.cancel()
    with suppress(asyncio.CancelledError):
        await consumer_task

    # 关闭 Consumer
    await stop_consumer()

    # 关闭 Producer
    await stop_producer()
    await engine.dispose()
app = FastAPI(title=PROJECT_NAME, version=PROJECT_VERSION, lifespan=lifespan)

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
async def root():
    return {"msg": "服务正常，文档地址 /docs"}

if __name__ == "__main__":
    import uvicorn
    reload_enabled = os.getenv("UVICORN_RELOAD", "false").lower() == "true"
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=reload_enabled)
@app.get("/test-kafka")
async def test_kafka():

    await send_message(
        topic="send_email",
        data={
            "email": "test@qq.com",
            "code": "123456"
        }
    )

    return {"msg": "发送成功"}
