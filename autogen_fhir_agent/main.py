#!/usr/bin/env python3
"""
NutriRec保健AI系统主入口
整合所有模块，提供统一的系统控制接口
"""

import asyncio
import logging
import os
import sys
import uvicorn
from pathlib import Path

# Add current directory to path
sys.path.append(os.path.dirname(__file__))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the core system
from core_system import SecureHealthcareAgentSystem
from security_handler import SecurityConfig

class NutriRecHealthcareSystem:
    """NutriRec医疗保健AI系统主类"""
    
    def __init__(self):
        """初始化NutriRec系统"""
        logger.info("🚀 启动NutriRec医疗保健AI系统...")
        
        # 配置安全系统
        security_config = SecurityConfig(
            enable_rate_limiting=True,
            enable_content_filtering=True,
            enable_audit_logging=True,
            max_requests_per_minute=60
        )
        
        # 初始化核心安全代理系统
        try:
            self.agent_system = SecureHealthcareAgentSystem(security_config)
            logger.info("✅ 安全代理系统初始化成功")
        except Exception as e:
            logger.error(f"❌ 安全代理系统初始化失败: {e}")
            raise
        
        # 获取FastAPI应用
        self.app = self.agent_system.app
        
        logger.info("🎉 NutriRec医疗保健AI系统初始化完成")
    
    async def process_consultation(
        self,
        session_id: str,
        user_id: str,
        query: str,
        scenario: str = "comprehensive_consultation"
    ):
        """处理咨询请求"""
        return await self.agent_system.process_contextual_consultation(
            session_id=session_id,
            user_id=user_id,
            query=query,
            scenario=scenario
        )
    
    def create_session(self, user_id: str = None, user_profile: dict = None) -> str:
        """创建用户会话"""
        return self.agent_system.create_conversation_session(user_id, user_profile)
    
    def get_user_preferences(self, session_id: str) -> dict:
        """获取用户偏好"""
        return self.agent_system.get_user_preferences(session_id)
    
    def run_server(self, host: str = "0.0.0.0", port: int = 8001, debug: bool = False):
        """运行服务器"""
        logger.info(f"🌐 启动NutriRec医疗AI服务器 - {host}:{port}")
        
        # 配置uvicorn
        config = uvicorn.Config(
            app=self.app,
            host=host,
            port=port,
            log_level="info" if not debug else "debug",
            reload=debug
        )
        
        server = uvicorn.Server(config)
        
        try:
            # 运行服务器
            asyncio.run(server.serve())
        except KeyboardInterrupt:
            logger.info("👋 收到停止信号，正在关闭服务器...")
        except Exception as e:
            logger.error(f"❌ 服务器运行错误: {e}")
            raise

def main():
    """主函数"""
    try:
        # 检查环境变量
        required_env_vars = ['OPENAI_API_KEY']
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        
        if missing_vars:
            logger.error(f"❌ 缺少必要的环境变量: {', '.join(missing_vars)}")
            logger.info("请设置以下环境变量:")
            for var in missing_vars:
                logger.info(f"  export {var}=your_key_here")
            sys.exit(1)
        
        # 创建并启动系统
        nutrirec_system = NutriRecHealthcareSystem()
        
        # 从命令行参数获取配置
        import argparse
        parser = argparse.ArgumentParser(description='NutriRec医疗保健AI系统')
        parser.add_argument('--host', default='0.0.0.0', help='服务器主机地址')
        parser.add_argument('--port', type=int, default=8001, help='服务器端口')
        parser.add_argument('--debug', action='store_true', help='启用调试模式')
        
        args = parser.parse_args()
        
        # 启动服务器
        nutrirec_system.run_server(
            host=args.host,
            port=args.port,
            debug=args.debug
        )
        
    except Exception as e:
        logger.error(f"❌ 系统启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()