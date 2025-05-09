import threading
import time
import logging
from typing import Dict, List, Optional, Any

from pkg.plugin.context import register, handler, content_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *

from autodl_client import AutoDLClient
from models import AutoDLConfig, GrabConfig, GrabMenuData, Instance
from storage import UserStorage

@register(name="AutoDLPlugin", description="AutoDL监控与抢卡助手", version="1.0.0", author="YourName")
class AutoDLPlugin(BasePlugin):
    def __init__(self, host: APIHost):
        super().__init__(host)
        self.host = host
        self.ap = host.ap
        
        # 用户配置
        self.storage = UserStorage("autodl_users.db")
        self.user_configs: Dict[int, AutoDLConfig] = {}
        
        # 抢卡任务
        self.grab_tasks: Dict[int, threading.Event] = {}
        self.grab_threads: Dict[int, threading.Thread] = {}
        
        # 加载所有用户配置
        self.user_configs = self.storage.load_all_users()
        
        self.host.logger.info("AutoDL插件初始化完成")
    
    # 异步初始化
    async def initialize(self):
        pass
    
    
    def _get_user_config(self, user_id: int) -> AutoDLConfig:
        """获取用户配置"""
        if user_id not in self.user_configs:
            self.user_configs[user_id] = AutoDLConfig()
        return self.user_configs[user_id]
    
    def _save_user_config(self, user_id: int, config: AutoDLConfig) -> None:
        """保存用户配置"""
        self.user_configs[user_id] = config
        self.storage.save_user(user_id, config)
    
    def _init_autodl_client(self, user_id: int) -> Optional[AutoDLClient]:
        """初始化AutoDL客户端"""
        config = self._get_user_config(user_id)
        if not config.username or not config.password:
            return None
        
        return AutoDLClient(config.username, config.password)
    
    # 命令处理
    @handler(on=EventContext.HANDLE_MESSAGE)
    def handle_message(self, ctx: EventContext):
        query = ctx.event.query
        msg = query.message
        user_id = query.sender.id
        
        # 命令处理
        if msg.startswith("/help"):
            self._send_help(query)
        elif msg.startswith("/user "):
            self._handle_user_command(query, msg[6:])
        elif msg.startswith("/password "):
            self._handle_password_command(query, msg[10:])
        elif msg.startswith("/gpuvalid"):
            self._handle_gpuvalid_command(query)
        elif msg.startswith("/instances"):
            self._handle_instances_command(query)
        elif msg.startswith("/start "):
            self._handle_start_command(query, msg[7:])
        elif msg.startswith("/startcpu "):
            self._handle_startcpu_command(query, msg[10:])
        elif msg.startswith("/stop "):
            self._handle_stop_command(query, msg[6:])
        elif msg.startswith("/refresh "):
            self._handle_refresh_command(query, msg[9:])
        elif msg.startswith("/refreshall"):
            self._handle_refreshall_command(query)
        elif msg.startswith("/getuser"):
            self._handle_getuser_command(query)
        elif msg.startswith("/balance"):
            self._handle_balance_command(query)
        elif msg.startswith("/grabmenu"):
            self._handle_grabmenu_command(query)
        elif msg.startswith("/grabgpu "):
            self._handle_grabgpu_command(query, msg[9:])
        elif msg.startswith("/grabuuid "):
            self._handle_grabuuid_command(query, msg[10:])
        elif msg.startswith("/stopgrab"):
            self._handle_stopgrab_command(query)
        elif msg.startswith("/grabstatus"):
            self._handle_grabstatus_command(query)
    
    # 帮助信息
    def _send_help(self, query):
        help_text = """AutoDL监控与抢卡助手

命令列表:
/user <用户名> - 设置用户名（手机号）
/password <密码> - 设置密码
/gpuvalid - 查看GPU空闲情况
/instances - 查看实例详情
/start <uuid> - 启动GPU实例
/startcpu <uuid> - 启动GPU实例(无卡模式)
/stop <uuid> - 关闭GPU实例
/refresh <uuid> - 无卡模式重置实例时长
/refreshall - 重置所有实例时长
/getuser - 查看当前设置的用户
/balance - 查看账户余额
/grabmenu - 显示抢卡菜单
/grabgpu <gpu类型> - 设置抢卡GPU型号并启动
/grabuuid <uuid> - 按实例UUID抢卡
/stopgrab - 停止抢卡任务
/grabstatus - 查看抢卡状态
"""
        query.respond(help_text)
    
    # 用户名设置
    def _handle_user_command(self, query, username):
        user_id = query.sender.id
        config = self._get_user_config(user_id)
        config.username = username
        self._save_user_config(user_id, config)
        query.respond(f"用户名已设置为: {username}")
    
    # 密码设置
    def _handle_password_command(self, query, password):
        user_id = query.sender.id
        config = self._get_user_config(user_id)
        config.password = password
        self._save_user_config(user_id, config)
        query.respond("密码已设置")
    
    # 查看GPU状态
    def _handle_gpuvalid_command(self, query):
        user_id = query.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            query.respond("请先设置用户名和密码")
            return
        
        query.respond("正在查询GPU状态...")
        instances = client.get_instances()
        
        if not instances:
            query.respond("获取实例信息失败")
            return
        
        result = "GPU状态:\n\n"
        for i, instance in enumerate(instances):
            result += f"机器: {instance.region_name}-{instance.machine_alias}\n"
            result += f"显卡: {instance.snapshot_gpu_alias_name}\n"
            result += f"UUID: {instance.uuid}\n"
            result += f"GPU数量: {instance.gpu_idle_num}/{instance.gpu_all_num}\n"
            
            # 显示释放时间
            stopped_at = instance.stopped_at
            if stopped_at and "time" in stopped_at:
                import datetime
                stop_time = stopped_at["time"]
                if stop_time:
                    # 计算剩余释放时间
                    try:
                        stop_datetime = datetime.datetime.fromisoformat(stop_time.replace('Z', '+00:00'))
                        release_time = stop_datetime + datetime.timedelta(hours=24)
                        now = datetime.datetime.now(datetime.timezone.utc)
                        if release_time > now:
                            remaining = release_time - now
                            hours = remaining.seconds // 3600
                            minutes = (remaining.seconds % 3600) // 60
                            result += f"释放时间: 还剩{hours}小时{minutes}分钟\n"
                    except:
                        pass
            
            if i < len(instances)-1:
                result += "----------------\n"
        
        query.respond(result)
    
    # 查看实例详情
    def _handle_instances_command(self, query):
        user_id = query.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            query.respond("请先设置用户名和密码")
            return
        
        query.respond("正在查询实例...")
        instances = client.get_instances()
        
        if not instances:
            query.respond("获取实例信息失败")
            return
        
        result = "实例列表:\n\n"
        for i, instance in enumerate(instances):
            result += f"{i+1}. {instance.region_name}-{instance.machine_alias}\n"
            result += f"显卡: {instance.snapshot_gpu_alias_name}\n"
            result += f"UUID: {instance.uuid}\n"
            result += f"GPU: {instance.gpu_idle_num}/{instance.gpu_all_num}\n"
            if i < len(instances)-1:
                result += "----------------\n"
        
        query.respond(result)
    
    # 启动实例
    def _handle_start_command(self, query, uuid):
        user_id = query.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            query.respond("请先设置用户名和密码")
            return
            
        if not uuid:
            query.respond("请提供实例UUID")
            return
        
        query.respond(f"正在启动实例 {uuid}...")
        success = client.power_on(uuid, use_cpu=False)
        
        if success:
            query.respond("实例启动成功")
        else:
            query.respond("实例启动失败")
    
    # 无卡模式启动实例
    def _handle_startcpu_command(self, query, uuid):
        user_id = query.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            query.respond("请先设置用户名和密码")
            return
            
        if not uuid:
            query.respond("请提供实例UUID")
            return
        
        query.respond(f"正在启动实例(无卡模式) {uuid}...")
        success = client.power_on(uuid, use_cpu=True)
        
        if success:
            query.respond("实例无卡启动成功")
        else:
            query.respond("实例无卡启动失败")
    
    # 关闭实例
    def _handle_stop_command(self, query, uuid):
        user_id = query.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            query.respond("请先设置用户名和密码")
            return
            
        if not uuid:
            query.respond("请提供实例UUID")
            return
        
        query.respond(f"正在关闭实例 {uuid}...")
        success = client.power_off(uuid)
        
        if success:
            query.respond("实例关闭成功")
        else:
            query.respond("实例关闭失败")
    
    # 刷新实例时长
    def _handle_refresh_command(self, query, uuid):
        user_id = query.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            query.respond("请先设置用户名和密码")
            return
            
        if not uuid:
            query.respond("请提供实例UUID")
            return
        
        query.respond(f"正在刷新实例时长 {uuid}...")
        
        # 先开启实例(无卡模式)
        start_success = client.power_on(uuid, use_cpu=True)
        if not start_success:
            query.respond("启动实例失败，无法刷新时长")
            return
        
        # 等待实例启动
        time.sleep(5)
        
        # 关闭实例
        stop_success = client.power_off(uuid)
        if not stop_success:
            query.respond("关闭实例失败，请手动关闭")
            return
            
        query.respond("实例时长刷新成功")
    
    # 刷新所有实例时长
    def _handle_refreshall_command(self, query):
        user_id = query.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            query.respond("请先设置用户名和密码")
            return
        
        query.respond("正在获取实例列表...")
        instances = client.get_instances()
        
        if not instances:
            query.respond("获取实例信息失败")
            return
        
        query.respond(f"开始刷新 {len(instances)} 个实例的时长...")
        
        for instance in instances:
            uuid = instance.uuid
            query.respond(f"正在刷新实例 {instance.machine_alias} ({uuid})...")
            
            # 开启实例(无卡模式)
            start_success = client.power_on(uuid, use_cpu=True)
            if not start_success:
                query.respond(f"启动实例 {uuid} 失败，跳过")
                continue
                
            # 等待实例启动
            time.sleep(5)
            
            # 关闭实例
            stop_success = client.power_off(uuid)
            if not stop_success:
                query.respond(f"关闭实例 {uuid} 失败，请手动关闭")
                continue
                
            query.respond(f"实例 {instance.machine_alias} 时长刷新成功")
            
            # 防止请求过快被限流
            time.sleep(3)
        
        query.respond("所有实例时长刷新完成")
    
    # 查看当前用户
    def _handle_getuser_command(self, query):
        user_id = query.sender.id
        config = self._get_user_config(user_id)
        
        if config.username:
            query.respond(f"当前设置的用户名: {config.username}")
        else:
            query.respond("当前未设置用户名")
    
    # 查看余额
    def _handle_balance_command(self, query):
        user_id = query.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            query.respond("请先设置用户名和密码")
            return
        
        balance = client.get_balance()
        if balance < 0:
            query.respond("获取余额失败")
        else:
            query.respond(f"账户余额: {balance} 元")
    
    # 抢卡菜单
    def _handle_grabmenu_command(self, query):
        user_id = query.sender.id
        
        menu_text = """抢卡功能使用说明:

1. 按GPU型号抢卡:
   /grabgpu <GPU型号>
   例如: /grabgpu A100

2. 按实例UUID抢卡:
   /grabuuid <UUID>
   例如: /grabuuid i-abcdef123456

3. 停止抢卡:
   /stopgrab

4. 查看抢卡状态:
   /grabstatus
"""
        query.respond(menu_text)
    
    # 按GPU型号抢卡
    def _handle_grabgpu_command(self, query, gpu_type):
        user_id = query.sender.id
        
        if not gpu_type:
            query.respond("请提供GPU型号")
            return
            
        # 停止可能存在的抢卡任务
        self._stop_grab_task(user_id)
        
        # 启动新的抢卡任务
        config = self._get_user_config(user_id)
        
        if not config.grab_config:
            config.grab_config = GrabConfig()
            
        config.grab_config.enabled = True
        config.grab_config.gpu_types = [gpu_type]
        config.grab_config.instance_uuid = ""
        config.grab_config.is_running = True
        
        self._save_user_config(user_id, config)
        
        # 启动抢卡线程
        self._start_grab_task(user_id, query)
        
        query.respond(f"已启动对 {gpu_type} 的抢卡任务")
    
    # 按实例UUID抢卡
    def _handle_grabuuid_command(self, query, uuid):
        user_id = query.sender.id
        
        if not uuid:
            query.respond("请提供实例UUID")
            return
            
        # 停止可能存在的抢卡任务
        self._stop_grab_task(user_id)
        
        # 启动新的抢卡任务
        config = self._get_user_config(user_id)
        
        if not config.grab_config:
            config.grab_config = GrabConfig()
            
        config.grab_config.enabled = True
        config.grab_config.gpu_types = []
        config.grab_config.instance_uuid = uuid
        config.grab_config.is_running = True
        
        self._save_user_config(user_id, config)
        
        # 启动抢卡线程
        self._start_grab_task(user_id, query)
        
        query.respond(f"已启动对实例 {uuid} 的抢卡任务")
    
    # 停止抢卡
    def _handle_stopgrab_command(self, query):
        user_id = query.sender.id
        
        if self._stop_grab_task(user_id):
            query.respond("抢卡任务已停止")
        else:
            query.respond("当前没有正在运行的抢卡任务")
    
    # 抢卡状态
    def _handle_grabstatus_command(self, query):
        user_id = query.sender.id
        config = self._get_user_config(user_id)
        
        if not config.grab_config or not config.grab_config.enabled:
            query.respond("抢卡任务未启动")
            return
            
        status = "正在运行" if config.grab_config.is_running else "已停止"
        
        status_text = f"抢卡任务状态: {status}\n"
        
        if config.grab_config.instance_uuid:
            status_text += f"抢卡实例UUID: {config.grab_config.instance_uuid}\n"
        elif config.grab_config.gpu_types:
            status_text += f"抢卡GPU型号: {', '.join(config.grab_config.gpu_types)}\n"
            
        status_text += f"检查间隔: {config.grab_config.check_interval}秒"
        
        query.respond(status_text)
    
    # 停止抢卡任务
    def _stop_grab_task(self, user_id: int) -> bool:
        if user_id in self.grab_tasks and self.grab_tasks[user_id] is not None:
            # 设置停止信号
            self.grab_tasks[user_id].set()
            
            # 更新用户配置
            config = self._get_user_config(user_id)
            if config.grab_config:
                config.grab_config.is_running = False
                self._save_user_config(user_id, config)
                
            # 清理资源
            if user_id in self.grab_threads:
                self.grab_threads[user_id].join(timeout=1.0)
                del self.grab_threads[user_id]
                
            del self.grab_tasks[user_id]
            return True
            
        return False
    
    # 启动抢卡任务
    def _start_grab_task(self, user_id: int, query) -> None:
        config = self._get_user_config(user_id)
        if not config.grab_config or not config.grab_config.enabled:
            return
            
        # 创建停止信号
        stop_signal = threading.Event()
        self.grab_tasks[user_id] = stop_signal
        
        # 创建并启动抢卡线程
        thread = threading.Thread(
            target=self._grab_task_loop,
            args=(user_id, query, stop_signal)
        )
        thread.daemon = True
        thread.start()
        
        self.grab_threads[user_id] = thread
    
    # 抢卡任务循环
    def _grab_task_loop(self, user_id: int, query, stop_signal: threading.Event) -> None:
        config = self._get_user_config(user_id)
        if not config.grab_config:
            return
            
        client = self._init_autodl_client(user_id)
        if not client:
            query.respond("抢卡失败: 未设置用户名或密码")
            self._stop_grab_task(user_id)
            return
            
        # 获取检查间隔
        interval = config.grab_config.check_interval
        if interval < 3:
            interval = 3  # 最小间隔3秒
            
        try:
            # 抢卡循环
            while not stop_signal.is_set():
                try:
                    # 按UUID抢卡
                    if config.grab_config.instance_uuid:
                        instances = client.get_instances()
                        target_uuid = config.grab_config.instance_uuid
                        
                        for instance in instances:
                            if instance.uuid == target_uuid and instance.gpu_idle_num > 0:
                                # 有空闲GPU，启动实例
                                success = client.power_on(target_uuid)
                                
                                if success:
                                    query.respond(f"抢卡成功: 实例 {target_uuid} 已启动")
                                    self._stop_grab_task(user_id)
                                    return
                                else:
                                    query.respond(f"抢卡失败: 实例 {target_uuid} 启动失败")
                    
                    # 按GPU型号抢卡
                    elif config.grab_config.gpu_types:
                        instances = client.get_instances()
                        target_types = config.grab_config.gpu_types
                        
                        for instance in instances:
                            if (instance.snapshot_gpu_alias_name in target_types or 
                                any(t in instance.snapshot_gpu_alias_name for t in target_types)) and \
                               instance.gpu_idle_num > 0:
                                # 有匹配的GPU且有空闲，启动实例
                                success = client.power_on(instance.uuid)
                                
                                if success:
                                    query.respond(f"抢卡成功: 实例 {instance.uuid} ({instance.snapshot_gpu_alias_name}) 已启动")
                                    self._stop_grab_task(user_id)
                                    return
                                else:
                                    query.respond(f"抢卡失败: 实例 {instance.uuid} 启动失败")
                
                except Exception as e:
                    self.host.logger.error(f"抢卡过程出错: {str(e)}")
                
                # 等待下一次检查
                stop_signal.wait(interval)
                
        except Exception as e:
            self.host.logger.error(f"抢卡任务异常: {str(e)}")
        finally:
            # 确保任务结束时更新状态
            config = self._get_user_config(user_id)
            if config.grab_config:
                config.grab_config.is_running = False
                self._save_user_config(user_id, config)
    
    # 插件初始化时重新启动之前的抢卡任务
    @handler(on=EventContext.INIT)
    def on_init(self, ctx: EventContext):
        for user_id, config in self.user_configs.items():
            if config.grab_config and config.grab_config.enabled and config.grab_config.is_running:
                # 创建一个简单的查询对象用于发送消息
                class SimpleQuery:
                    def __init__(self, user_id, host):
                        self.sender = type('obj', (object,), {'id': user_id})
                        self.host = host
                    
                    def respond(self, message):
                        self.host.send_message(user_id, message)
                
                query = SimpleQuery(user_id, self.host)
                self.host.logger.info(f"为用户 {user_id} 重启抢卡任务")
                self._start_grab_task(user_id, query)
                query.respond("系统重启，抢卡任务已自动恢复")

    # 内容函数：查询GPU状态
    @content_func("check_autodl_gpu", 
        description="检查用户AutoDL平台上的GPU资源和实例情况",
        parameters=[])
    async def check_autodl_gpu_func(self, query_obj) -> str:
        user_id = query_obj.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            return "请先设置您的AutoDL账户。使用 /user 和 /password 命令设置用户名和密码。"
        
        try:
            instances = client.get_instances()
            if not instances:
                return "无法获取您的实例信息，请检查账号设置是否正确。"
            
            result = "🖥️ 您的AutoDL实例情况：\n\n"
            available_gpus = 0
            
            for i, instance in enumerate(instances):
                result += f"📊 {instance.region_name}-{instance.machine_alias}\n"
                result += f"🔌 显卡: {instance.snapshot_gpu_alias_name}\n"
                result += f"🆔 UUID: {instance.uuid}\n"
                result += f"🎮 GPU状态: {instance.gpu_idle_num}/{instance.gpu_all_num} 可用\n"
                
                if instance.gpu_idle_num > 0:
                    available_gpus += 1
                    
                if i < len(instances)-1:
                    result += "----------------\n"
            
            # 添加总结信息
            if available_gpus > 0:
                result += f"\n✅ 总结: 您有 {available_gpus} 个实例有可用GPU"
            else:
                result += "\n❌ 总结: 目前没有可用的GPU资源"
                
            return result
            
        except Exception as e:
            self.host.logger.error(f"查询GPU状态出错: {str(e)}")
            return f"查询GPU状态时出错: {str(e)}"

    # 内容函数：启动实例
    @content_func("start_autodl_instance", 
        description="启动用户的AutoDL实例",
        parameters=[
            {"name": "uuid", "description": "要启动的实例UUID", "required": True},
            {"name": "use_cpu", "description": "是否使用无卡模式启动", "required": False}
        ])
    async def start_autodl_instance_func(self, uuid: str, use_cpu: bool = False) -> str:
        query_obj = getattr(self, "current_query", None)
        if not query_obj:
            return "操作失败：无法获取用户信息"
            
        user_id = query_obj.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            return "请先设置您的AutoDL账户。使用 /user 和 /password 命令设置用户名和密码。"
        
        try:
            if not uuid:
                return "请提供要启动的实例UUID"
                
            success = client.power_on(uuid, use_cpu=use_cpu)
            
            if success:
                mode = "无卡模式" if use_cpu else "普通模式"
                return f"✅ 实例 {uuid} 已成功启动({mode})"
            else:
                return f"❌ 实例 {uuid} 启动失败，请检查UUID是否正确或实例状态"
                
        except Exception as e:
            self.host.logger.error(f"启动实例出错: {str(e)}")
            return f"启动实例时出错: {str(e)}"

    # 内容函数：关闭实例
    @content_func("stop_autodl_instance", 
        description="关闭用户的AutoDL实例",
        parameters=[
            {"name": "uuid", "description": "要关闭的实例UUID", "required": True}
        ])
    async def stop_autodl_instance_func(self, uuid: str) -> str:
        query_obj = getattr(self, "current_query", None)
        if not query_obj:
            return "操作失败：无法获取用户信息"
            
        user_id = query_obj.sender.id
        client = self._init_autodl_client(user_id)
        
        if not client:
            return "请先设置您的AutoDL账户。使用 /user 和 /password 命令设置用户名和密码。"
        
        try:
            if not uuid:
                return "请提供要关闭的实例UUID"
                
            success = client.power_off(uuid)
            
            if success:
                return f"✅ 实例 {uuid} 已成功关闭"
            else:
                return f"❌ 实例 {uuid} 关闭失败，请检查UUID是否正确或实例状态"
                
        except Exception as e:
            self.host.logger.error(f"关闭实例出错: {str(e)}")
            return f"关闭实例时出错: {str(e)}"

    # 内容函数：抢卡
    @content_func("grab_autodl_gpu", 
        description="设置并启动AutoDL抢卡任务",
        parameters=[
            {"name": "gpu_type", "description": "要抢的GPU型号，如A100", "required": False},
            {"name": "uuid", "description": "要抢的实例UUID", "required": False},
            {"name": "interval", "description": "检查间隔(秒)，最小3秒", "required": False}
        ])
    async def grab_autodl_gpu_func(self, gpu_type: str = "", uuid: str = "", interval: int = 5) -> str:
        query_obj = getattr(self, "current_query", None)
        if not query_obj:
            return "操作失败：无法获取用户信息"
            
        user_id = query_obj.sender.id
        
        if not gpu_type and not uuid:
            return "请至少提供一个GPU型号或实例UUID"
            
        # 防止间隔过小
        if interval < 3:
            interval = 3
            
        # 停止现有抢卡任务
        self._stop_grab_task(user_id)
        
        # 设置新的抢卡配置
        config = self._get_user_config(user_id)
        
        if not config.grab_config:
            config.grab_config = GrabConfig()
            
        config.grab_config.enabled = True
        config.grab_config.is_running = True
        config.grab_config.check_interval = interval
        
        if uuid:
            config.grab_config.instance_uuid = uuid
            config.grab_config.gpu_types = []
            grab_target = f"实例 {uuid}"
        else:
            config.grab_config.instance_uuid = ""
            config.grab_config.gpu_types = [gpu_type]
            grab_target = f"GPU型号 {gpu_type}"
            
        self._save_user_config(user_id, config)
        
        # 启动抢卡任务
        self._start_grab_task(user_id, query_obj)
        
        return f"✅ 已开始抢卡：{grab_target}，检查间隔 {interval} 秒"
        
    # 内容函数：停止抢卡
    @content_func("stop_autodl_grab", 
        description="停止正在运行的AutoDL抢卡任务",
        parameters=[])
    async def stop_autodl_grab_func(self) -> str:
        query_obj = getattr(self, "current_query", None)
        if not query_obj:
            return "操作失败：无法获取用户信息"
            
        user_id = query_obj.sender.id
        
        if self._stop_grab_task(user_id):
            return "✅ 抢卡任务已停止"
        else:
            return "❌ 当前没有正在运行的抢卡任务"
            
    # 设置当前查询对象（用于内容函数）
    @handler(on=EventContext.BEFORE_FUNC_CALLING)
    def before_func_calling(self, ctx: EventContext):
        self.current_query = ctx.event.query
        
    @handler(on=EventContext.AFTER_FUNC_CALLING)
    def after_func_calling(self, ctx: EventContext):
        self.current_query = None

    # 插件卸载时触发
    def __del__(self):
        # 停止所有抢卡任务
        for user_id in list(self.grab_tasks.keys()):
            self._stop_grab_task(user_id)
        
        # 保存所有用户配置
        for user_id, config in self.user_configs.items():
            self.storage.save_user(user_id, config)