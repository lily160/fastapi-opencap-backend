import os
from dotenv import load_dotenv

load_dotenv()


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


# 数据库
DB_URL = os.getenv("DB_URL") or os.getenv("DATABASE_URL", "mysql+pymysql://root@127.0.0.1:3306/opencap?charset=utf8mb4")
DB_ECHO = os.getenv("DB_ECHO", "False") == "True"

# JWT
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-before-production")
ALGORITHM = os.getenv("ALGORITHM") or os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_SECONDS = env_int("ACCESS_EXPIRE_SEC", env_int("ACCESS_TOKEN_EXPIRE_SECONDS", 3600))
REFRESH_TOKEN_DAYS = env_int("REFRESH_EXPIRE_DAY", env_int("REFRESH_TOKEN_EXPIRE_DAYS", 7))

# 算法服务
ALGO_BASE_URL = os.getenv("ALGO_BASE_URL", "http://127.0.0.1:9000")
ALGO_API_KEY = os.getenv("ALGO_API_KEY")
ALGO_TIMEOUT = env_int("ALGO_TIMEOUT", 30)

# 文件存储【修改：统一归集到storage根目录，新增metadata目录】
BASE_STORAGE = os.path.join(os.getcwd(), "storage")
UPLOAD_DIR = os.path.join(BASE_STORAGE, "uploads")
RESULT_DIR = os.path.join(BASE_STORAGE, "results")
METADATA_DIR = os.path.join(BASE_STORAGE, "metadata") # 【新增】metadata.yaml存储路径
LOG_DIR = os.path.join(BASE_STORAGE, "logs")

MAX_VIDEO_SIZE = env_int("MAX_VIDEO_SIZE", 1024 * 1024 * 1024)
VIDEO_ALLOW = set(os.getenv("ALLOW_VIDEO_SUFFIX", ".mp4,.mov,.avi").split(","))
CONFIG_ALLOW = set(os.getenv("CONFIG_SUFFIX", ".json,.yaml,.yml").split(","))

# 定时任务
POLL_INTERVAL = env_int("POLL_INTERVAL", 10)
TASK_MAX_TIMEOUT_SEC = 1800 # 【新增】任务全局超时阈值，与算法30分钟超时对齐

# 超级管理员
SUPER_ADMIN_USERNAME = os.getenv("SUPER_ADMIN_USER")
SUPER_ADMIN_RAW_PWD = os.getenv("SUPER_ADMIN_PWD")

# 【新增：忘记密码流程超时参数，读取.env配置】
FORGOT_LOOKUP_EXPIRE = env_int("FORGOT_LOOKUP_EXPIRE", 300)
FORGOT_CODE_EXPIRE = env_int("FORGOT_CODE_EXPIRE", 300)
FORGOT_CODE_INTERVAL = env_int("FORGOT_CODE_INTERVAL", 60)
FORGOT_MAX_RETRY = env_int("FORGOT_MAX_RETRY", 5)

# FastAPI app
PROJECT_NAME = os.getenv("PROJECT_NAME", "opencap")
PROJECT_VERSION = os.getenv("PROJECT_VERSION", "1.6")
