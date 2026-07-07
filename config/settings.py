import os
from dotenv import load_dotenv

load_dotenv()

# 数据库
DB_URL = os.getenv("DB_URL")
DB_ECHO = os.getenv("DB_ECHO", "False") == "True"

# JWT
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_SECONDS = int(os.getenv("ACCESS_EXPIRE_SEC"))
REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_EXPIRE_DAY"))

# 算法服务
ALGO_BASE_URL = os.getenv("ALGO_BASE_URL")
ALGO_API_KEY = os.getenv("ALGO_API_KEY")
ALGO_TIMEOUT = int(os.getenv("ALGO_TIMEOUT"))

# 文件存储【修改：统一归集到storage根目录，新增metadata目录】
BASE_STORAGE = os.path.join(os.getcwd(), "storage")
UPLOAD_DIR = os.path.join(BASE_STORAGE, "uploads")
RESULT_DIR = os.path.join(BASE_STORAGE, "results")
METADATA_DIR = os.path.join(BASE_STORAGE, "metadata") # 【新增】metadata.yaml存储路径
LOG_DIR = os.path.join(BASE_STORAGE, "logs")

MAX_VIDEO_SIZE = int(os.getenv("MAX_VIDEO_SIZE"))
VIDEO_ALLOW = set(os.getenv("ALLOW_VIDEO_SUFFIX").split(","))
CONFIG_ALLOW = set(os.getenv("CONFIG_SUFFIX").split(","))

# 定时任务
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL"))
TASK_MAX_TIMEOUT_SEC = 1800 # 【新增】任务全局超时阈值，与算法30分钟超时对齐

# 超级管理员
SUPER_ADMIN_USERNAME = os.getenv("SUPER_ADMIN_USER")
SUPER_ADMIN_RAW_PWD = os.getenv("SUPER_ADMIN_PWD")

# 【新增：忘记密码流程超时参数，读取.env配置】
FORGOT_LOOKUP_EXPIRE = int(os.getenv("FORGOT_LOOKUP_EXPIRE"))
FORGOT_CODE_EXPIRE = int(os.getenv("FORGOT_CODE_EXPIRE"))
FORGOT_CODE_INTERVAL = int(os.getenv("FORGOT_CODE_INTERVAL"))
FORGOT_MAX_RETRY = int(os.getenv("FORGOT_MAX_RETRY"))