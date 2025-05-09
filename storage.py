import os
import json
import sqlite3
from typing import Dict, Any, Optional

from models import AutoDLConfig

class UserStorage:
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建用户表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            password TEXT,
            config TEXT
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_user(self, user_id: int, config: AutoDLConfig) -> bool:
        """保存用户配置"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            config_json = config.model_dump_json()
            
            cursor.execute(
                "INSERT OR REPLACE INTO users (user_id, username, password, config) VALUES (?, ?, ?, ?)",
                (user_id, config.username, config.password, config_json)
            )
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"保存用户配置失败: {e}")
            return False
    
    def load_user(self, user_id: int) -> Optional[AutoDLConfig]:
        """加载用户配置"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT config FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            
            conn.close()
            
            if result:
                return AutoDLConfig.model_validate_json(result[0])
            return AutoDLConfig()
        except Exception as e:
            print(f"加载用户配置失败: {e}")
            return AutoDLConfig()
    
    def load_all_users(self) -> Dict[int, AutoDLConfig]:
        """加载所有用户配置"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT user_id, config FROM users")
            results = cursor.fetchall()
            
            conn.close()
            
            user_configs = {}
            for user_id, config_json in results:
                user_configs[user_id] = AutoDLConfig.model_validate_json(config_json)
            
            return user_configs
        except Exception as e:
            print(f"加载所有用户配置失败: {e}")
            return {}