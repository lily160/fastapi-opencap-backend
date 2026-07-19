import uuid

def generate_uuid() -> str:
    """
    生成全局唯一UUID字符串，用于 file_id / config_id / result_id 等唯一标识
    格式：36位标准UUID4字符串（带分隔符），全局不重复
    """
    return str(uuid.uuid4())