import os
import yaml
from config.settings import METADATA_DIR
from core.exceptions import CustomException
from config.constants import CODE_SERVER_ERR


def generate_metadata_yaml(task_id: str, height_m: float, mass_kg: float, sex: str, activity: str,
                           custom_metadata: dict = None) -> str:
    """
    根据前端传入的参数，在本地生成 metadata.yaml 文件，供算法读取
    返回生成文件的绝对物理路径
    """
    try:
        # 1. 按照算法要求的结构组装字典
        data = {
            "subject": {
                "height_m": height_m,
                "mass_kg": mass_kg,
                "sex": sex
            },
            "trial": {
                "activity": activity
            }
        }

        # 2. 如果前端传了自定义字段，统一塞进 custom_fields
        if custom_metadata:
            data["custom_fields"] = custom_metadata

        # 3. 拼接安全的文件路径 (使用 task_id 作为文件名防止冲突)
        file_name = f"{task_id}_metadata.yaml"
        file_path = os.path.join(METADATA_DIR, file_name)

        # 4. 写入 YAML 文件
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        return file_path

    except Exception as e:
        raise CustomException(status_code=CODE_SERVER_ERR, detail=f"生成 metadata 配置文件失败: {str(e)}")