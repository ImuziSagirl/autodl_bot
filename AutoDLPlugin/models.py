from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

# AutoDL接口数据模型
class LoginRequest(BaseModel):
    phone: str
    password: str
    v_code: str = ""
    phone_area: str = "+86"
    picture_id: Optional[dict] = None

class Instance(BaseModel):
    machine_alias: str
    region_name: str
    gpu_all_num: int
    gpu_idle_num: int
    uuid: str
    snapshot_gpu_alias_name: str
    stopped_at: Optional[dict] = None

# 用户配置模型
class AutoDLConfig(BaseModel):
    username: str = ""
    password: str = ""
    grab_config: Optional["GrabConfig"] = None

# 抢卡配置模型
class GrabConfig(BaseModel):
    enabled: bool = False
    gpu_types: List[str] = []
    instance_uuid: str = ""
    check_interval: int = 5
    is_running: bool = False

# 抢卡菜单数据
class GrabMenuData(BaseModel):
    gpu_type: str = ""
    instance_uuid: str = ""
    check_interval: int = 5
    available_gpus: List[str] = []
    instances: List[Instance] = []