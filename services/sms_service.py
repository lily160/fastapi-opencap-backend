import asyncio
import json
import logging

from alibabacloud_dysmsapi20170525 import models as dysms_models
from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
from alibabacloud_tea_openapi import models as open_api_models

from config.settings import (
    SMS_ACCESS_KEY_ID,
    SMS_ACCESS_KEY_SECRET,
    SMS_ENDPOINT,
    SMS_SIGN_NAME,
    SMS_TEMPLATE_CODE,
)

logger = logging.getLogger(__name__)


class SMSService:
    def __init__(self):
        self._configured = all((
            SMS_ACCESS_KEY_ID,
            SMS_ACCESS_KEY_SECRET,
            SMS_SIGN_NAME,
            SMS_TEMPLATE_CODE,
        ))
        config = open_api_models.Config(
            access_key_id=SMS_ACCESS_KEY_ID,
            access_key_secret=SMS_ACCESS_KEY_SECRET,
            endpoint=SMS_ENDPOINT,
        )
        self.client = DysmsapiClient(config)

    async def send_sms(self, phone: str, code: str) -> bool:
        if not self._configured:
            raise RuntimeError("SMS service is not fully configured")

        request = dysms_models.SendSmsRequest(
            phone_numbers=phone,
            sign_name=SMS_SIGN_NAME,
            template_code=SMS_TEMPLATE_CODE,
            template_param=json.dumps({"code": code}),
        )
        try:
            response = await asyncio.to_thread(self.client.send_sms, request)
        except Exception as exc:
            logger.exception("Alibaba Cloud SMS request failed")
            raise RuntimeError("SMS provider request failed") from exc

        if response.body.code != "OK":
            logger.error(
                "Alibaba Cloud SMS rejected request: code=%s, message=%s, request_id=%s",
                response.body.code,
                response.body.message,
                getattr(response.body, "request_id", None),
            )
            raise RuntimeError(f"SMS provider rejected the request: {response.body.code}")
        logger.info(
            "Alibaba Cloud SMS request accepted: request_id=%s",
            getattr(response.body, "request_id", None),
        )
        return True


sms_service = SMSService()
