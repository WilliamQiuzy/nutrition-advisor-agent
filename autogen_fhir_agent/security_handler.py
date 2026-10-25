"""
安全处理模块
负责安全配置、安全检查、中间件设置等功能
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

class SecurityLevel(Enum):
    STANDARD = "standard"
    HIGH = "high"

@dataclass 
class SecurityConfig:
    enable_rate_limiting: bool = True
    enable_content_filtering: bool = True
    enable_audit_logging: bool = True
    max_requests_per_minute: int = 60

class SecurityHandler:
    """安全处理器"""
    
    def __init__(self, security_config: SecurityConfig = None):
        self.security_config = security_config or SecurityConfig()
        self.request_counts: Dict[str, list] = {}  # 简单的请求计数器
    
    async def process_security_check(self, request_id: str, user_id: str, content: str) -> Tuple[bool, str]:
        """简化的安全检查"""
        try:
            # 基本验证
            if not user_id or len(user_id) < 3:
                return False, "Invalid user ID"
            
            if not content or len(content.strip()) == 0:
                return False, "Empty content"
            
            # 简单的频率限制
            now = datetime.now()
            
            if user_id not in self.request_counts:
                self.request_counts[user_id] = []
            
            # 清理1分钟前的记录
            self.request_counts[user_id] = [
                timestamp for timestamp in self.request_counts[user_id]
                if now - timestamp < timedelta(minutes=1)
            ]
            
            # 检查频率限制
            if len(self.request_counts[user_id]) >= self.security_config.max_requests_per_minute:
                return False, "Rate limit exceeded"
            
            # 记录这次请求
            self.request_counts[user_id].append(now)
            
            return True, "Valid"
            
        except Exception as e:
            logger.error(f"Security check error: {e}")
            return False, "Security check failed"
    
    def setup_security_middleware(self, app: FastAPI):
        """设置安全中间件"""
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def get_safe_error_message(self, reason: str) -> str:
        """Get user-friendly error message"""
        error_messages = {
            "rate_limit": "您的请求过于频繁，请稍后再试。",
            "malicious": "您的请求包含不当内容，请重新描述您的需求。",
            "cost_limit": "系统暂时繁忙，请稍后再试。",
            "invalid_input": "请描述您的健康咨询需求。"
        }
        
        for key, message in error_messages.items():
            if key in reason.lower():
                return message
        
        return "抱歉，系统暂时无法处理您的请求。请稍后再试或联系客服。" 