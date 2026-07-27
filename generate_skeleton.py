import os

# 定义所有需要创建的目录
directories = [
    "config",
    "database/models",
    "schemas/common",
    "schemas/auth",
    "schemas/upload",
    "schemas/task",
    "schemas/admin",
    "schemas/algo_inner",
    "routers",
    "internal_routers",
    "core",
    "utils",
    "storage/uploads",
    "storage/metadata",
    "storage/results",
    "storage/logs",
    "migrations",
    "tests",
    "static"
]

# 定义所有需要创建的文件
files = [
    ".gitignore", "README.md", "requirements.txt", ".env", "alembic.ini", "main.py",
    "config/__init__.py", "config/settings.py", "config/constants.py",
    "database/__init__.py", "database/db.py",
    "database/models/__init__.py", "database/models/sys_user.py", "database/models/sys_upload_file.py",
    "database/models/sys_task.py", "database/models/sys_task_result.py", "database/models/sys_camera_config.py",
    "database/models/sys_token_blacklist.py", "database/models/sys_operation_log.py",
    "database/models/sys_permission.py",
    "database/models/sys_role_permission.py", "database/models/sys_user_permission_override.py",
    "schemas/__init__.py", "schemas/common/__init__.py", "schemas/common/common_schema.py",
    "schemas/auth/__init__.py", "schemas/auth/auth_schema.py",
    "schemas/upload/__init__.py", "schemas/upload/upload_schema.py",
    "schemas/task/__init__.py", "schemas/task/task_schema.py",
    "schemas/admin/__init__.py", "schemas/admin/admin_schema.py",
    "schemas/algo_inner/__init__.py", "schemas/algo_inner/algo_inner_schema.py",
    "routers/__init__.py", "routers/auth.py", "routers/upload.py", "routers/task.py", "routers/download.py",
    "routers/admin.py",
    "internal_routers/__init__.py", "internal_routers/algo.py",
    "core/__init__.py", "core/exceptions.py", "core/security.py", "core/rbac_permission.py", "core/algo_client.py",
    "core/task_poller.py", "core/file_security.py", "core/yaml_generator.py", "core/id_wrapper.py",
    "core/log_middleware.py",
    "utils/__init__.py", "utils/time_util.py", "utils/response_util.py", "utils/uuid_util.py", "utils/validator_util.py"
]


def create_project_structure():
    print("开始生成项目骨架...")

    # 1. 创建目录
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"创建目录: {directory}/")

    # 2. 创建空文件
    for file in files:
        # 确保文件所在的父目录存在 (双重保险)
        parent_dir = os.path.dirname(file)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        # 创建空文件，如果已存在则跳过以防覆盖
        if not os.path.exists(file):
            with open(file, 'w', encoding='utf-8') as f:
                pass
            print(f"创建文件: {file}")
        else:
            print(f"文件已存在, 跳过: {file}")

    print("\n✅ 项目骨架生成完毕！")


if __name__ == "__main__":
    create_project_structure()