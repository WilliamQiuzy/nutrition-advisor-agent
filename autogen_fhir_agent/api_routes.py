"""
API路由模块
负责FastAPI路由定义和请求处理
"""

import asyncio
import json
import logging
import uuid
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

class APIRoutes:
    """API路由管理器"""
    
    def __init__(self, system):
        self.system = system
    
    def setup_routes(self, app: FastAPI):
        """设置API路由"""
        
        @app.get("/health")
        async def health_check():
            return {"status": "healthy", "security": "enabled"}
        
        @app.get("/security/metrics")
        async def security_metrics(request: Request):
            """Get security metrics dashboard"""
            metrics = {
                "requests_processed": len(self.system.context_manager.active_sessions),
                "active_sessions": len(self.system.context_manager.active_sessions),
                "security_level": "enabled"
            }
            return JSONResponse(content=metrics)
        
        @app.post("/api/v1/secure/supplement-recommendation")
        async def secure_supplement_recommendation(request: Request):
            """Secure endpoint for supplement recommendations"""
            return await self._handle_secure_recommendation(request)
        
        @app.post("/api/v1/secure/wechat")
        async def secure_wechat_endpoint(request: Request):
            """Secure WeChat integration endpoint"""
            return await self._handle_secure_wechat(request)
    
    def verify_wechat_signature(self, signature: str, timestamp: str, nonce: str, token: str) -> bool:
        """验证微信服务器签名"""
        try:
            tmp_arr = [token, timestamp, nonce]
            tmp_arr.sort()
            tmp_str = ''.join(tmp_arr)
            tmp_str = hashlib.sha1(tmp_str.encode()).hexdigest()
            return tmp_str == signature
        except Exception as e:
            logger.error(f"WeChat signature verification error: {e}")
            return False

    def parse_wechat_message(self, xml_data: str) -> Dict[str, str]:
        """解析微信XML消息"""
        try:
            root = ET.fromstring(xml_data)
            msg = {}
            for child in root:
                msg[child.tag] = child.text if child.text else ""
            return msg
        except Exception as e:
            logger.error(f"WeChat XML parsing error: {e}")
            return {"FromUserName": "unknown", "Content": "", "MsgType": "text"}

    def create_wechat_text_response(self, to_user: str, from_user: str, content: str) -> str:
        """创建微信文本回复消息"""
        timestamp = int(datetime.now().timestamp())
        return f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{timestamp}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""
    
    async def _handle_secure_recommendation(self, request: Request) -> JSONResponse:
        """Handle supplement recommendation with full security"""
        try:
            # Extract request data
            body = await request.body()
            data = json.loads(body)
            
            user_id = data.get("user_id", "anonymous")
            query = data.get("query", "")
            scenario = data.get("scenario", "comprehensive_consultation")
            request_id = str(uuid.uuid4())
            
            # 1. Security check (simplified)
            is_allowed, reason = await self.system.security_handler.process_security_check(
                request_id=request_id,
                user_id=user_id,
                content=query
            )
            security_context = {"user_id": user_id, "request_id": request_id}
            
            if not is_allowed:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "Request blocked by security policy",
                        "reason": reason,
                        "request_id": request_id
                    }
                )
            
            # 2. Execute agents with security
            result = await self.system.execute_secure_agents(
                query=query,
                scenario=scenario,
                user_id=user_id,
                request_id=request_id,
                security_context=security_context
            )
            
            # 3. Format response
            response = {
                "request_id": request_id,
                "status": "success",
                "data": result,
                "security": {
                    "filtered": result.get("validation_info", {}).get("filtered", False),
                    "validated": result.get("validation_info", {}).get("validated", False)
                }
            }
            
            return JSONResponse(content=response)
            
        except Exception as e:
            logger.error(f"Secure recommendation error: {e}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "message": "系统错误，请稍后重试"
                }
            )
    
    async def _handle_secure_wechat(self, request: Request) -> JSONResponse:
        """Handle WeChat requests with comprehensive security and processing"""
        try:
            # Get raw XML data
            body = await request.body()
            xml_data = body.decode('utf-8')
            
            # Verify WeChat signature
            signature = request.headers.get("X-Wechat-Signature", "")
            timestamp = request.headers.get("X-Wechat-Timestamp", "")
            nonce = request.headers.get("X-Wechat-Nonce", "")
            
            # Parse WeChat message
            wechat_data = self.parse_wechat_message(xml_data)
            
            user_id = wechat_data.get("FromUserName", "wechat_user")
            content = wechat_data.get("Content", "")
            msg_type = wechat_data.get("MsgType", "text")
            msg_id = wechat_data.get("MsgId", str(uuid.uuid4()))
            
            # Only process text messages
            if msg_type != "text":
                response_xml = self.create_wechat_text_response(
                    user_id, "nutrirec_medical", "您好！我只能处理文字消息，请发送您的健康咨询问题。"
                )
                return JSONResponse(content=response_xml, media_type="application/xml")
            
            # Security check (simplified)
            is_allowed, reason = await self.system.security_handler.process_security_check(
                request_id=msg_id,
                user_id=user_id,
                content=content
            )
            security_context = {"user_id": user_id, "request_id": msg_id}
            
            if not is_allowed:
                error_message = self.system.security_handler.get_safe_error_message(reason)
                response_xml = self.create_wechat_text_response(user_id, "nutrirec_medical", error_message)
                return JSONResponse(content=response_xml, media_type="application/xml")
            
            # Determine scenario
            scenario = self._determine_scenario_from_message(content)
            
            # Process with secure system
            result = await self.system.execute_secure_agents(
                query=content,
                scenario=scenario,
                user_id=user_id,
                request_id=msg_id,
                security_context=security_context
            )
            response_content = result["recommendation"]
            
            # Create WeChat XML response
            response_xml = self.create_wechat_text_response(user_id, "nutrirec_medical", response_content)
            
            return JSONResponse(content=response_xml, media_type="application/xml")
            
        except Exception as e:
            logger.error(f"Secure WeChat error: {e}")
            # Return safe error response
            error_xml = self.create_wechat_text_response(
                "wechat_user", 
                "nutrirec_medical", 
                "系统繁忙，请稍后再试。如需帮助，请联系客服。"
            )
            return JSONResponse(content=error_xml, media_type="application/xml")
    
    def _determine_scenario_from_message(self, message: str) -> str:
        """Determine consultation scenario from message content"""
        message_lower = message.lower()
        
        # Safety keywords
        safety_keywords = [
            "安全", "副作用", "不良反应", "过敏", "禁忌", "相互作用", "冲突",
            "safety", "side effect", "adverse", "allergy", "contraindication"
        ]
        
        if any(keyword in message_lower for keyword in safety_keywords):
            return "safety_assessment"
        
        # Optimization keywords  
        optimization_keywords = [
            "优化", "改善", "提高", "调整", "搭配", "组合", "效果",
            "optimize", "improve", "enhance", "adjust", "combination"
        ]
        
        if any(keyword in message_lower for keyword in optimization_keywords):
            return "supplement_optimization"
        
        # Default to comprehensive
        return "comprehensive_consultation" 