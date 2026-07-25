import json
import logging

from aiokafka import AIOKafkaConsumer

from config.settings import KAFKA_BOOTSTRAP_SERVERS, KAFKA_FORGOT_PASSWORD_TOPIC
from services.email_service import send_email

logger = logging.getLogger(__name__)

consumer: AIOKafkaConsumer | None = None


async def start_consumer():
    global consumer
    if consumer is None:
        consumer = AIOKafkaConsumer(
            KAFKA_FORGOT_PASSWORD_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        )
    await consumer.start()
    print("Kafka Consumer 已启动")


async def stop_consumer():
    global consumer
    if consumer is not None:
        await consumer.stop()
        consumer = None
    print("Kafka Consumer 已关闭")


async def consume():
    if consumer is None:
        raise RuntimeError("Kafka Consumer has not been started")
    async for msg in consumer:
        data = json.loads(msg.value.decode("utf-8"))
        if (
            data.get("event") == "forgot_password_code"
            and data.get("contact_type") == "email"
        ):
            await send_email(email=data["email"], code=data["code"])
            logger.info("Forgot-password verification email sent")
        else:
            logger.warning(
                "Ignored unsupported Kafka event: event=%s, contact_type=%s",
                data.get("event"),
                data.get("contact_type"),
            )
