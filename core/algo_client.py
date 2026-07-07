import httpx
from fastapi import HTTPException
from config.settings import ALGO_BASE_URL, ALGO_API_KEY, ALGO_TIMEOUT
from config.constants import CODE_SERVER_ERR

def cancel_algo_task(algo_id: str):
    """调用算法服务取消指定algo_id的运行/排队任务"""
    headers = {
        "X-API-Key": ALGO_API_KEY,
        "Content-Type": "application/json"
    }
    url = f"{ALGO_BASE_URL}/cancel/{algo_id}"
    try:
        with httpx.Client(timeout=ALGO_TIMEOUT/2) as client:
            resp = client.post(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "success":
                raise HTTPException(CODE_SERVER_ERR, f"算法取消失败: {data.get('message')}")
    except httpx.HTTPError as e:
        raise HTTPException(CODE_SERVER_ERR, f"调用算法取消接口异常: {str(e)}")