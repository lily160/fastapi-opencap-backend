import json

from aiokafka import AIOKafkaProducer

from config.settings import KAFKA_BOOTSTRAP_SERVERS


producer: AIOKafkaProducer | None = None


async def start_producer():
    global producer
    if producer is None:
        producer = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
    await producer.start()
    print("Kafka Producer 已启动")


async def stop_producer():
    global producer
    if producer is not None:
        await producer.stop()
        producer = None
    print("Kafka Producer 已关闭")


async def send_message(topic: str, data: dict):
    if producer is None:
        raise RuntimeError("Kafka Producer has not been started")
    await producer.send_and_wait(topic, json.dumps(data).encode("utf-8"))
