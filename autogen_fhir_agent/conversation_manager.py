"""
对话管理和上下文处理模块
负责会话管理、消息存储、用户偏好提取等功能
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ConversationMessage:
    """对话消息数据结构"""
    role: str  # user, assistant, system
    content: str
    timestamp: str
    agent_type: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class ConversationContext:
    """对话上下文管理"""
    session_id: str
    user_id: Optional[str] = None
    messages: Optional[List[ConversationMessage]] = None
    user_profile: Optional[Dict[str, Any]] = None
    preferences: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

class ConversationContextManager:
    """对话上下文管理器"""
    
    def __init__(self):
        self.active_sessions: Dict[str, ConversationContext] = {}
        self.max_session_duration = 3600  # 1小时
        self.max_messages_per_session = 100
    
    def create_session(self, user_id: Optional[str] = None, user_profile: Optional[Dict] = None) -> str:
        """创建新的对话会话"""
        session_id = str(uuid.uuid4())
        context = ConversationContext(
            session_id=session_id,
            user_id=user_id,
            user_profile=user_profile or {}
        )
        self.active_sessions[session_id] = context
        logger.info(f"创建新对话会话: {session_id}")
        return session_id
    
    def add_message(self, session_id: str, role: str, content: str, 
                   agent_type: Optional[str] = None, metadata: Optional[Dict] = None):
        """添加消息到对话历史"""
        if session_id in self.active_sessions:
            message = ConversationMessage(
                role=role,
                content=content,
                timestamp=datetime.now().isoformat(),
                agent_type=agent_type,
                metadata=metadata
            )
            context = self.active_sessions[session_id]
            if context.messages is None:
                context.messages = []
            context.messages.append(message)
            context.updated_at = datetime.now().isoformat()
            
            # 限制消息数量
            if context.messages and len(context.messages) > self.max_messages_per_session:
                context.messages = context.messages[-self.max_messages_per_session:]
                
            logger.debug(f"添加消息到会话 {session_id}: {role} - {content[:50]}...")
    
    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        """获取对话上下文"""
        return self.active_sessions.get(session_id)
    
    def get_recent_messages(self, session_id: str, count: int = 10) -> List[ConversationMessage]:
        """获取最近的消息"""
        context = self.get_context(session_id)
        if context:
            return context.messages[-count:] if context.messages else []
        return []
    
    def extract_user_preferences(self, session_id: str) -> Dict[str, Any]:
        """从对话历史中提取用户偏好"""
        context = self.get_context(session_id)
        if not context or not context.messages:
            return {}
        
        preferences = {}
        
        # 分析用户消息，提取偏好信息
        user_messages = [msg for msg in context.messages if msg.role == "user"]
        
        # 地理位置偏好
        cities = ['北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安', '南京', '天津']
        for msg in user_messages:
            for city in cities:
                if city in msg.content:
                    preferences['preferred_city'] = city
                    break
        
        # 医疗偏好
        if any('儿科' in msg.content or '孩子' in msg.content or '小孩' in msg.content 
               for msg in user_messages):
            preferences['has_children'] = True
        
        if any('老人' in msg.content or '父母' in msg.content or '老年' in msg.content 
               for msg in user_messages):
            preferences['elderly_care'] = True
        
        # 健康关注点
        health_keywords = {
            'heart': ['心脏', '胸痛', '心悸'],
            'digestive': ['肠胃', '消化', '腹痛'],
            'respiratory': ['呼吸', '咳嗽', '肺'],
            'orthopedic': ['关节', '骨头', '腰痛']
        }
        
        for category, keywords in health_keywords.items():
            if any(keyword in msg.content for msg in user_messages for keyword in keywords):
                if 'health_concerns' not in preferences:
                    preferences['health_concerns'] = []
                preferences['health_concerns'].append(category)
        
        return preferences
    
    def cleanup_expired_sessions(self):
        """清理过期会话"""
        current_time = datetime.now()
        expired_sessions = []
        
        for session_id, context in self.active_sessions.items():
            if context.created_at:
                created_time = datetime.fromisoformat(context.created_at)
                if (current_time - created_time).seconds > self.max_session_duration:
                    expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self.active_sessions[session_id]
            logger.info(f"清理过期会话: {session_id}")
    
    def format_context_for_agents(self, session_id: str) -> Optional[str]:
        """格式化上下文供agents使用"""
        context = self.get_context(session_id)
        if not context or not context.messages:
            return None
        
        # 获取最近的对话
        recent_messages = self.get_recent_messages(session_id, 10)
        
        # 格式化为JSON字符串
        formatted_messages = []
        for msg in recent_messages:
            formatted_msg = {
                "role": msg.role,
                "content": msg.content,
                "timestamp": msg.timestamp
            }
            if msg.agent_type:
                formatted_msg["agent_type"] = msg.agent_type
            formatted_messages.append(formatted_msg)
        
        return json.dumps(formatted_messages, ensure_ascii=False) 