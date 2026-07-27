class CustomException(Exception):
    """
    全局自定义业务异常类
    用于在业务逻辑中主动抛出，后续由 FastAPI 的全局异常处理器统一捕获并返回标准 JSON
    """
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.detail)