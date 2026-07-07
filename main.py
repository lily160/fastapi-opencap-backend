import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 业务路由
from routers import api_router
# 【修改：独立导入内部算法路由，不混入/api/v1前缀】
from internal_routers.algo import algo_router
from database.db import engine, Base
from config.settings import BASE_STORAGE, UPLOAD_DIR, RESULT_DIR, METADATA_DIR, LOG_DIR
from core.task_poller import start_scheduler

# 导入全部表模型,自动建表
from database.models import (
    sys_user, sys_upload_file, sys_task, sys_task_result,
    sys_camera_config, sys_token_blacklist, sys_operation_log,
    sys_permission, sys_role_permission, sys_user_permission_override
)

# 【修改：修复原代码变量错误 RESULT → RESULT_DIR，新增METADATA_DIR、LOG_DIR初始化】
init_folders = [BASE_STORAGE, UPLOAD_DIR, RESULT_DIR, METADATA_DIR, LOG_DIR]
for folder in init_folders:
    os.makedirs(folder, exist_ok=True)

# 创建数据表
Base.metadata.create_all(bind=engine)

# 启动定时轮询任务
start_scheduler()

app = FastAPI(title="OpenCap Monocular V1.6 后端", version="1.6")
# 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
# 业务接口前缀 /api/v1
app.include_router(api_router, prefix="/api/v1")
# 【修改：算法内部接口无前缀，单独挂载，不会混入/api/v1路由分组】
app.include_router(algo_router)

@app.get("/")
def root():
    return {"msg": "服务正常,文档地址 /api/v1/docs"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)