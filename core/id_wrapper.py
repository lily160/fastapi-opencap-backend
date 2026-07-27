import hashlib
from core.exceptions import CustomException
from config.constants import CODE_PARAM_ERR


def generate_task_id(algo_id: str) -> str:
    """
    基于算法原始 algo_id 包装生成前端感知的 task_id。
    规则：前缀(oc-) + algo_id + 哈希后缀，确保唯一性与安全性，全程不对外暴露原始 algo_id。
    """
    if not algo_id:
        raise CustomException(status_code=CODE_PARAM_ERR, detail="生成 task_id 失败：原始 algo_id 不能为空")

    # 生成一个简单的短哈希作为后缀，增加安全性，防止被恶意遍历猜测
    hash_suffix = hashlib.md5(algo_id.encode('utf-8')).hexdigest()[:6]

    # 组装对外暴露的 task_id (例如: oc-job-a7f9-2b4c-a1b2c3)
    safe_task_id = f"oc-{algo_id}-{hash_suffix}"

    return safe_task_id