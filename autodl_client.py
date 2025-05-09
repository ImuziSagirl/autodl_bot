import requests
import hashlib
import time
import logging
from typing import List, Dict, Any, Optional

from models import Instance

class AutoDLClient:
    BASE_URL = "https://www.autodl.com/api/v1"
    LOGIN_PATH = "/new_login"
    PASSPORT_PATH = "/passport"
    INSTANCE_PATH = "/instance"
    POWER_ON_PATH = "/instance/power_on"
    POWER_OFF_PATH = "/instance/power_off"
    BALANCE_PATH = "/wallet"
    
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = self._hash_password(password)
        self.token = ""
        self.client = requests.Session()
        self.client.headers.update({
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "appversion": "v5.56.0",
            "content-type": "application/json;charset=UTF-8",
            "sec-ch-ua": "\"Chromium\";v=\"130\", \"Google Chrome\";v=\"130\", \"Not?A_Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
        })
    
    def _hash_password(self, password: str) -> str:
        """密码SHA1哈希"""
        sha1 = hashlib.sha1()
        sha1.update(password.encode('utf-8'))
        return sha1.hexdigest()
    
    def login(self) -> bool:
        """登录AutoDL获取token"""
        try:
            # 登录请求获取ticket
            login_data = {
                "phone": self.username,
                "password": self.password,
                "v_code": "",
                "phone_area": "+86",
                "picture_id": None
            }
            
            response = self.client.post(f"{self.BASE_URL}{self.LOGIN_PATH}", json=login_data)
            login_resp = response.json()
            
            if login_resp.get("code") != "Success":
                logging.error(f"登录失败: {login_resp.get('msg')}")
                return False
                
            ticket = login_resp["data"]["ticket"]
            
            # 获取token
            passport_data = {"ticket": ticket}
            response = self.client.post(f"{self.BASE_URL}{self.PASSPORT_PATH}", json=passport_data)
            passport_resp = response.json()
            
            if passport_resp.get("code") != "Success":
                logging.error(f"获取token失败: {passport_resp.get('msg')}")
                return False
                
            self.token = passport_resp["data"]["token"]
            logging.info(f"用户{self.username}登录成功，获取到token")
            return True
            
        except Exception as e:
            logging.error(f"登录出错: {str(e)}")
            return False
    
    def get_instances(self) -> List[Instance]:
        """获取实例列表"""
        if not self.token:
            if not self.login():
                return []
        
        try:
            instance_data = {
                "date_from": "",
                "date_to": "",
                "page_index": 1,
                "page_size": 10,
                "status": [],
                "charge_type": []
            }
            
            response = self.client.post(
                f"{self.BASE_URL}{self.INSTANCE_PATH}",
                json=instance_data,
                headers={"authorization": self.token}
            )
            resp = response.json()
            
            # 检查token是否过期
            if resp.get("code") == "AuthorizeFailed":
                # 重新登录
                if not self.login():
                    return []
                
                # 重新请求
                response = self.client.post(
                    f"{self.BASE_URL}{self.INSTANCE_PATH}",
                    json=instance_data,
                    headers={"authorization": self.token}
                )
                resp = response.json()
            
            if resp.get("code") != "Success":
                logging.error(f"获取实例失败: {resp.get('msg')}")
                return []
            
            instances = [Instance(**inst) for inst in resp["data"]["list"]]
            return instances
            
        except Exception as e:
            logging.error(f"获取实例出错: {str(e)}")
            return []

    def power_on(self, uuid: str, use_cpu: bool = False) -> bool:
        """启动实例"""
        if not self.token:
            if not self.login():
                return False
        
        try:
            power_data = {"instance_uuid": uuid}
            if use_cpu:
                power_data["restart_type"] = "cpu"
            
            response = self.client.post(
                f"{self.BASE_URL}{self.POWER_ON_PATH}",
                json=power_data,
                headers={"authorization": self.token}
            )
            
            resp = response.json()
            # 处理token过期
            if resp.get("code") == "AuthorizeFailed":
                if not self.login():
                    return False
                response = self.client.post(
                    f"{self.BASE_URL}{self.POWER_ON_PATH}",
                    json=power_data,
                    headers={"authorization": self.token}
                )
                resp = response.json()
            
            return resp.get("code") == "Success"
            
        except Exception as e:
            logging.error(f"启动实例出错: {str(e)}")
            return False
            
    def power_off(self, uuid: str) -> bool:
        """关闭实例"""
        if not self.token:
            if not self.login():
                return False
        
        try:
            power_data = {"instance_uuid": uuid}
            response = self.client.post(
                f"{self.BASE_URL}{self.POWER_OFF_PATH}",
                json=power_data,
                headers={"authorization": self.token}
            )
            
            resp = response.json()
            # 处理token过期
            if resp.get("code") == "AuthorizeFailed":
                if not self.login():
                    return False
                response = self.client.post(
                    f"{self.BASE_URL}{self.POWER_OFF_PATH}",
                    json=power_data,
                    headers={"authorization": self.token}
                )
                resp = response.json()
            
            return resp.get("code") == "Success"
            
        except Exception as e:
            logging.error(f"关闭实例出错: {str(e)}")
            return False
    
    def get_balance(self) -> float:
        """获取余额"""
        if not self.token:
            if not self.login():
                return -1
                
        try:
            response = self.client.get(
                f"{self.BASE_URL}{self.BALANCE_PATH}",
                headers={"authorization": self.token}
            )
            
            resp = response.json()
            if resp.get("code") == "AuthorizeFailed":
                if not self.login():
                    return -1
                response = self.client.get(
                    f"{self.BASE_URL}{self.BALANCE_PATH}",
                    headers={"authorization": self.token}
                )
                resp = response.json()
                
            if resp.get("code") != "Success":
                return -1
                
            return float(resp["data"]["assets"]) / 100
            
        except Exception as e:
            logging.error(f"获取余额出错: {str(e)}")
            return -1