import httpx
from fastapi import HTTPException
from config.settings import ALGO_BASE_URL, ALGO_API_KEY, TASK_MAX_TIMEOUT_SEC, ALGO_TIMEOUT
from core.exceptions import CustomException
from config.constants import CODE_SERVER_ERR

class AlgoClient:
    def __init__(self):
        self.base_url = ALGO_BASE_URL
        self.headers = {"X-API-Key": ALGO_API_KEY}
        # 算法运行慢，设置长超时（默认 1800 秒 / 30 分钟）
        self.timeout = httpx.Timeout(TASK_MAX_TIMEOUT_SEC)

    async def run_mono(self, payload: dict) -> dict:  # 👈 注意这里的返回值提示建议改成 dict
        """
        提交算法任务，死等并返回算法侧包含所有文件路径的结果字典
        """
        # 增加 trust_env=False 绕过系统代理
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/run_mono",
                    json=payload,
                    headers=self.headers
                )
                response.raise_for_status()

                # 🚨 核心修改：直接返回整个完整的 JSON 字典，不要再去取不存在的 algo_id 了！
                return response.json()

            except httpx.HTTPError as e:
                # 捕获外部调用异常，防止后端崩溃
                raise CustomException(
                    status_code=CODE_SERVER_ERR,
                    detail=f"算法服务调用失败: {str(e)}"
                )
    async def get_status(self, algo_id: str) -> dict:
        """
        供后台定时任务轮询进度的接口
        """
        # 【修改点 2】: 增加 trust_env=False, proxies=None 绕过系统代理
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            response = await client.get(
                f"{self.base_url}/status/{algo_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

algo_client = AlgoClient()

def cancel_algo_task(algo_id: str):
    """调用算法服务取消指定algo_id的运行/排队任务"""
    headers = {
        "X-API-Key": ALGO_API_KEY,
        "Content-Type": "application/json"
    }
    url = f"{ALGO_BASE_URL}/cancel/{algo_id}"
    try:
        # 【修改点 3】: 同步客户端也增加 trust_env=False, proxies=None 绕过系统代理
        with httpx.Client(timeout=ALGO_TIMEOUT/2, trust_env=False) as client:
            resp = client.post(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") != "success":
                raise HTTPException(CODE_SERVER_ERR, f"算法取消失败: {data.get('message')}")
    except httpx.HTTPError as e:
        raise HTTPException(CODE_SERVER_ERR, f"调用算法取消接口异常: {str(e)}")