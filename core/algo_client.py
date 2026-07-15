import httpx
from config.settings import ALGO_BASE_URL, ALGO_API_KEY, TASK_MAX_TIMEOUT_SEC
from core.exceptions import CustomException
from config.constants import CODE_SERVER_ERR

class AlgoClient:
    def __init__(self):
        self.base_url = ALGO_BASE_URL
        self.headers = {"X-API-Key": ALGO_API_KEY}
        # 算法运行慢，设置长超时（默认 1800 秒 / 30 分钟）
        self.timeout = httpx.Timeout(TASK_MAX_TIMEOUT_SEC)

    async def run_mono(self, payload: dict) -> str:
        """
        提交算法任务，返回算法侧的 algo_id
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/run_mono",
                    json=payload,
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()
                return data.get("algo_id")
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
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{self.base_url}/status/{algo_id}",
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()

algo_client = AlgoClient()