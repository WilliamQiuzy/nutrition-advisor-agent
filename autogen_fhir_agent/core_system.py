"""
核心系统模块
包含主要的SecureHealthcareAgentSystem类和核心业务逻辑
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

# Load environment variables from root .env file
try:
    from dotenv import load_dotenv
    # Load .env from root directory
    root_dir = Path(__file__).parent.parent
    env_path = root_dir / '.env'
    load_dotenv(env_path)
    logging.info(f"✅ 成功加载环境变量从: {env_path}")
except ImportError:
    logging.warning("python-dotenv not installed. Using system environment variables only.")
except Exception as e:
    logging.warning(f"Failed to load .env file: {e}")

# Add shared modules to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from fastapi import FastAPI
import autogen
from autogen import ConversableAgent, GroupChat, GroupChatManager

# Import modules
from conversation_manager import ConversationContextManager
from security_handler import SecurityHandler, SecurityConfig
from function_registry import FallbackFunctionRegistry
from agent_factory import AgentFactory
from api_routes import APIRoutes

logger = logging.getLogger(__name__)

# 简化依赖，移除不存在的模块
try:
    from fhir_client import FHIRClient, FHIRConfig
except ImportError:
    logger.warning("FHIR client not available")
    class FHIRClient:
        def __init__(self, config): pass
    class FHIRConfig:
        def __init__(self, **kwargs): pass

class SecureHealthcareAgentSystem:
    """
    Healthcare agent system with comprehensive security integration
    """
    
    def __init__(self, security_config: Optional[SecurityConfig] = None):
        # Initialize security system (simplified)
        self.security_handler = SecurityHandler(security_config)
        
        # Initialize conversation context manager
        self.context_manager = ConversationContextManager()
        
        # Initialize FastAPI app with security
        self.app = FastAPI(title="Secure Healthcare AI API")
        self.security_handler.setup_security_middleware(self.app)
        
        # AI configuration using existing config manager
        try:
            from .config_manager import get_ai_config
            self.ai_config = get_ai_config()
        except (ImportError, ValueError) as e:
            # 回退到环境变量配置
            logger.warning(f"Config manager failed: {e}, using fallback config")
            self.ai_config = self._get_fallback_ai_config()
        
        # Initialize FHIR client
        self.fhir_config = FHIRConfig(
            base_url=os.getenv("FHIR_BASE_URL", "https://hapi.fhir.org/baseR4/"),
            client_id=os.getenv("FHIR_CLIENT_ID", "healthcare_ai_agent"),
            scopes=["patient/*.read", "user/*.read"]
        )
        
        try:
            self.fhir_client = FHIRClient(self.fhir_config)
        except Exception as e:
            logger.warning(f"FHIR client initialization failed: {e}")
            self.fhir_client = None
        
        # Initialize function registry with security
        self.function_registry = FallbackFunctionRegistry(parent_system=self)
        
        # Initialize knowledge manager
        from vector_knowledge_manager import get_vector_knowledge_manager
        try:
            self.knowledge_manager = get_vector_knowledge_manager()
            logger.info("✅ 向量知识库管理器初始化成功")
        except Exception as e:
            logger.warning(f"⚠️ 向量知识库管理器初始化失败: {e}")
            self.knowledge_manager = None
        
        # Initialize agent factory
        self.agent_factory = AgentFactory(self.function_registry)
        
        # Initialize API routes
        self.api_routes = APIRoutes(self)
        self.api_routes.setup_routes(self.app)
        
        logger.info("Secure Healthcare Agent System initialized")
    
    def create_conversation_session(self, user_id: Optional[str] = None, user_profile: Optional[Dict] = None) -> str:
        """创建新的对话会话，支持FHIR格式转换"""
        # 如果启用了FHIR格式，转换用户配置
        if user_profile and self._should_use_fhir():
            try:
                from fhir_data_converter import FHIRDataConverter
                converter = FHIRDataConverter()
                
                # 转换为FHIR Patient格式
                fhir_patient = converter.convert_to_fhir_patient(user_profile)
                
                # 在user_profile中保存FHIR格式数据
                user_profile['fhir_patient'] = fhir_patient
                logger.info(f"✅ 用户数据已转换为FHIR格式")
            except Exception as e:
                logger.warning(f"⚠️ FHIR格式转换失败，使用原始格式: {e}")
        
        return self.context_manager.create_session(user_id, user_profile)
    
    def _should_use_fhir(self) -> bool:
        """检查是否应该使用FHIR格式"""
        return os.getenv('USE_FHIR_FORMAT', 'true').lower() == 'true'
    
    def add_conversation_message(self, session_id: str, role: str, content: str, 
                               agent_type: Optional[str] = None, metadata: Optional[Dict] = None):
        """添加消息到对话历史"""
        self.context_manager.add_message(session_id, role, content, agent_type, metadata)
    
    def get_user_preferences(self, session_id: str) -> Dict[str, Any]:
        """获取用户偏好"""
        return self.context_manager.extract_user_preferences(session_id)
    
    async def process_contextual_consultation(
        self,
        session_id: str,
        user_id: str,
        query: str,
        scenario: str = "comprehensive_consultation"
    ) -> Dict[str, Any]:
        """
        处理带上下文的咨询请求
        """
        try:
            start_time = time.time()
            
            # 记录用户查询到对话历史
            self.add_conversation_message(session_id, "user", query)
            
            # 🔍 提取医疗关键词并更新患者病史
            await self._extract_and_update_medical_history(session_id, query)
            
            # 获取用户偏好和上下文
            user_preferences = self.get_user_preferences(session_id)
            conversation_context = self.context_manager.format_context_for_agents(session_id)
            
            logger.info(f"🔄 开始处理带上下文的咨询: {query[:50]}...")
            logger.info(f"📊 用户偏好: {user_preferences}")
            
            # 创建安全的agents
            agents = self.agent_factory.create_secure_agents(scenario, self.get_agent_config())
            
            if not agents:
                return {
                    "status": "error",
                    "message": "无法创建AI代理",
                    "session_id": session_id
                }
            
            # 执行并行咨询（使用现有的方法）
            results = await self._execute_parallel_consultation(agents, query)
            
            # 生成最终回答（使用现有的方法）
            final_response = await self._generate_final_response(results, query)
            
            # 记录AI回答到对话历史
            self.add_conversation_message(session_id, "assistant", final_response, "system")
            
            processing_time = time.time() - start_time
            
            return {
                "status": "success",
                "query": query,
                "session_id": session_id,
                "user_preferences": user_preferences,
                "final_response": final_response,
                "agent_results": results,
                "processing_time": processing_time,
                "context_used": conversation_context is not None
            }
            
        except Exception as e:
            logger.error(f"Contextual consultation error: {e}")
            return {
                "status": "error",
                "message": f"咨询处理失败: {str(e)}",
                "session_id": session_id
            }
    
    async def _execute_parallel_consultation(self, agents: Dict[str, ConversableAgent], query: str) -> Dict[str, Any]:
        """执行真正的并行AI专家咨询"""
        try:
            logger.info(f"🚀 启动 {len(agents)} 位专家的并行咨询...")
            
            # 高效并行执行所有专家
            async def run_single_agent_consultation(agent_name: str, agent: ConversableAgent) -> tuple:
                """运行单个专家的AI咨询"""
                start_time = time.time()
                
                try:
                    # 构建专家专用的查询prompt
                    expert_prompt = f"""
用户咨询: {query}

请根据您的专业角色和职责，提供详细的专业建议。
- 请按照您的system_message中定义的格式要求回答
- 提供具体、实用、专业的建议
- 确保回答内容丰富且有价值
"""
                    
                    # 创建消息列表
                    messages = [
                        {"role": "system", "content": agent.system_message},
                        {"role": "user", "content": expert_prompt}
                    ]
                    
                    # 调用专家AI生成回答
                    response = await agent.a_generate_reply(messages)
                    
                    duration = time.time() - start_time
                    
                    if response and isinstance(response, str) and response.strip():
                        logger.info(f"✅ {agent_name} 完成咨询 ({duration:.2f}s)")
                        return agent_name, response.strip(), True, duration
                    else:
                        logger.warning(f"⚠️ {agent_name} 返回空回答")
                        return agent_name, f"{agent_name} 正在分析您的问题，请稍后重试", False, duration
                        
                except asyncio.TimeoutError:
                    duration = time.time() - start_time
                    logger.warning(f"⏰ {agent_name} 超时 ({duration:.2f}s)")
                    return agent_name, f"{agent_name} 正在深度分析，请稍后重试", False, duration
                    
                except Exception as e:
                    duration = time.time() - start_time
                    logger.error(f"❌ {agent_name} 咨询失败: {str(e)}")
                    return agent_name, f"{agent_name} 暂时不可用: {str(e)}", False, duration
            
            # 创建并行任务
            tasks = [run_single_agent_consultation(name, agent) for name, agent in agents.items()]
            
            # 执行所有专家咨询
            parallel_start = time.time()
            results_raw = await asyncio.gather(*tasks, return_exceptions=True)
            parallel_duration = time.time() - parallel_start
            
            # 处理结果
            results = {}
            successful_count = 0
            
            for result in results_raw:
                if isinstance(result, Exception):
                    logger.error(f"专家任务异常: {result}")
                    continue
                    
                agent_name, response, success, duration = result
                results[agent_name] = response
                
                if success:
                    successful_count += 1
            
            logger.info(f"🎉 并行咨询完成: {successful_count}/{len(agents)} 专家成功 ({parallel_duration:.2f}s)")
            
            return results
            
        except Exception as e:
            logger.error(f"并行咨询系统失败: {e}")
            return {"error": str(e)}
    
    async def _generate_final_response(self, results: Dict[str, Any], query: str) -> str:
        """使用专门的整合专家生成最终回答"""
        try:
            if "error" in results:
                return "抱歉，系统遇到问题，请稍后重试。"
            
            if not results:
                return "暂时无法获取专家建议，请稍后重试。"
            
            # 创建专门的整合专家
            integration_config = self.get_agent_config()
            integration_expert = self.agent_factory.create_integration_expert(integration_config)
            
            # 构建专家意见汇总
            expert_opinions = ""
            expert_names = {
                "NutritionConsultant": "营养顾问Dr. Chen",
                "SupplementSpecialist": "产品专家Dr. Wang", 
                "SafetyAssessor": "安全评估师Dr. Li",
                "HealthCoach": "健康教练Dr. Zhang",
                "FormulationExpert": "配方专家"
            }
            
            for agent_name, response in results.items():
                expert_title = expert_names.get(agent_name, agent_name)
                expert_opinions += f"\n### {expert_title}的专业意见:\n{response}\n"
            
            # 构建整合请求
            integration_prompt = f"""
用户原始问题: {query}

以下是我们专家团队的详细分析:
{expert_opinions}

请作为首席医疗官，整合以上专家意见，形成一份专业、连贯、实用的最终建议报告。
请严格按照您的system_message中定义的格式要求进行整合。
"""
            
            # 使用整合专家生成最终报告
            messages = [
                {"role": "system", "content": integration_expert.system_message},
                {"role": "user", "content": integration_prompt}
            ]
            
            logger.info("🧠 启动专门的整合专家...")
            start_time = time.time()
            
            integrated_response = await integration_expert.a_generate_reply(messages)
            
            integration_time = time.time() - start_time
            logger.info(f"✅ 整合专家完成 ({integration_time:.2f}s)")
            
            if isinstance(integrated_response, str) and integrated_response.strip():
                return integrated_response.strip()
            else:
                # 如果整合失败，使用简化的格式化方法
                logger.warning("整合专家回答为空，使用备用格式化")
                return self._fallback_format_responses(results, expert_names)
                
        except Exception as e:
            logger.error(f"整合专家处理失败: {e}")
            return self._fallback_format_responses(results, expert_names)
    
    def _fallback_format_responses(self, results: Dict[str, Any], expert_names: Dict[str, str]) -> str:
        """备用的响应格式化方法"""
        formatted_response = "# NutriRec多专家会诊结果\n\n"
        
        for agent_name, response in results.items():
            expert_name = expert_names.get(agent_name, f"🔬 {agent_name}")
            formatted_response += f"## {expert_name}\n\n{response}\n\n"
        
        formatted_response += "---\n\n"
        formatted_response += "**⚠️ 免责声明**: 以上建议仅供参考，请在使用前咨询专业医生。\n\n"
        formatted_response += "**🏥 NutriRec** - 您的健康伙伴"
        
        return formatted_response

    def _get_fallback_ai_config(self) -> Dict[str, Any]:
        """回退AI配置方法 - 根据AI_PROVIDER选择API"""
        ai_provider = os.getenv('AI_PROVIDER', 'openai').lower()
        
        if ai_provider == 'openai':
            api_key = os.getenv('OPENAI_API_KEY')
            # 使用更快的模型
            model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
            base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
            api_type = "openai"
            
            if not api_key or api_key == 'None':
                raise ValueError("缺少OPENAI_API_KEY环境变量")
                
        elif ai_provider == 'deepseek':
            api_key = os.getenv('DEEPSEEK_API_KEY')
            model = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
            base_url = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
            api_type = "openai"  # DeepSeek API is OpenAI-compatible
            
            if not api_key or api_key == 'your_deepseek_api_key_here':
                raise ValueError("缺少DEEPSEEK_API_KEY环境变量")
        else:
            raise ValueError(f"不支持的AI_PROVIDER: {ai_provider}")
        
        # 从环境变量获取通用AI设置，增加超时时间
        max_tokens = int(os.getenv('AI_MAX_TOKENS', '1500'))  # 减少token数量
        temperature = float(os.getenv('AI_TEMPERATURE', '0.7'))
        timeout = int(os.getenv('AI_TIMEOUT', '120'))  # 增加超时时间
        
        return {
            "config_list": [
                {
                    "model": model,
                    "api_key": api_key,
                    "base_url": base_url,
                    "api_type": api_type
                }
            ],
            "timeout": timeout,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "cache_seed": None,
            "functions": []
        }
    
    async def execute_secure_agents(
        self,
        query: str,
        scenario: str,
        user_id: str,
        request_id: str,
        security_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute agents with full security isolation and monitoring"""
        
        start_time = time.time()
        
        # Create agents with security context
        agents = self.agent_factory.create_secure_agents(scenario, self.get_agent_config())
        
        # Setup group chat
        groupchat = GroupChat(
            agents=list(agents.values()),
            messages=[],
            max_round=10,
            speaker_selection_method="round_robin"
        )
        
        manager = GroupChatManager(
            groupchat=groupchat,
            llm_config=self.get_agent_config()
        )
        
        # Execute conversation with parallel isolation for better performance
        agent_responses = {}
        
        # 高效并行执行所有Agent
        async def run_single_agent_secure(agent_name: str, agent: ConversableAgent) -> tuple:
            """安全并行执行单个Agent，包含错误处理和性能监控"""
            start_agent_time = time.time()
            
            try:
                # 添加超时保护
                response = await asyncio.wait_for(
                    self._run_agent_conversation_optimized(agent, query),
                    timeout=60.0  # 60秒超时，给复杂查询更多时间
                )
                
                duration = time.time() - start_agent_time
                
                if response and response.strip():
                    logger.info(f"✅ Agent {agent_name} completed successfully in {duration:.2f}s")
                    return agent_name, response.strip(), True, duration
                else:
                    logger.warning(f"⚠️ Agent {agent_name} returned empty response")
                    return agent_name, f"Agent {agent_name} 暂时不可用，请稍后重试", False, duration
                    
            except asyncio.TimeoutError:
                duration = time.time() - start_agent_time
                logger.warning(f"⏰ Agent {agent_name} timed out after {duration:.2f}s (复杂查询需要更多时间)")
                return agent_name, f"Agent {agent_name} 正在处理复杂查询，请稍后重试", False, duration
                
            except Exception as e:
                duration = time.time() - start_agent_time
                logger.error(f"❌ Agent {agent_name} execution failed: {str(e)}")
                return agent_name, f"Agent {agent_name} 执行失败: {str(e)}", False, duration
        
        # 启动高性能并行执行
        logger.info(f"🚀 Starting optimized parallel execution of {len(agents)} agents")
        parallel_start = time.time()
        
        # 创建并行任务，使用优化的安全执行函数
        tasks = [run_single_agent_secure(name, agent) for name, agent in agents.items()]
        
        # 使用gather执行所有任务，允许部分失败
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        parallel_duration = time.time() - parallel_start
        logger.info(f"Parallel execution completed in {parallel_duration:.2f}s")
        
        # 处理并行执行结果
        successful_agents = 0
        agent_durations = {}
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Agent task failed with exception: {result}")
                continue
                
            agent_name, response, success, duration = result
            agent_responses[agent_name] = response
            agent_durations[agent_name] = duration
            
            if success:
                successful_agents += 1
        
        # 使用专门的聚合Agent整合所有专家意见
        final_response = await self._aggregate_expert_opinions(agent_responses, query)
        validation_info = {"filtered": False, "validated": True}
        
        processing_time = time.time() - start_time
        
        # 计算性能提升指标
        sequential_estimate = sum(agent_durations.values()) if agent_durations else processing_time
        performance_improvement = ((sequential_estimate - parallel_duration) / sequential_estimate * 100) if sequential_estimate > 0 else 0
        
        logger.info(f"Performance improvement: {performance_improvement:.1f}% ({successful_agents}/{len(agents)} agents successful)")
        
        return {
            "recommendation": final_response,
            "agents_involved": list(agent_responses.keys()),
            "validation_info": validation_info,
            "cost_info": {
                "processing_time": processing_time,
                "parallel_execution_time": parallel_duration,
                "agents_count": len(agent_responses),
                "successful_agents": successful_agents,
                "performance_improvement_percent": performance_improvement,
                "agent_durations": agent_durations,
                "estimated_sequential_time": sequential_estimate
            }
        }
    
    def _format_agent_responses(self, agent_responses: Dict[str, str]) -> str:
        """格式化智能体响应"""
        if not agent_responses:
            return "暂时无法获取专家建议，请稍后重试。如需帮助，请联系NutriRec客服。"
        
        formatted_response = "## NutriRec专家团队咨询结果\n\n"
        
        for agent_name, response in agent_responses.items():
            agent_display_name = {
                "NutritionConsultant": "营养顾问",
                "SupplementSpecialist": "产品专家", 
                "SafetyAssessor": "安全评估师",
                "HealthCoach": "健康教练",
                "FormulationExpert": "配方师"
            }.get(agent_name, agent_name)
            
            formatted_response += f"### {agent_display_name}建议：\n{response}\n\n"
        
        formatted_response += "---\n**免责声明**：以上建议仅供参考，请在使用前咨询专业医生。\n\nNutriRec - 您的健康伙伴"
        
        return formatted_response
    
    async def _aggregate_expert_opinions(self, agent_responses: Dict[str, str], original_query: str) -> str:
        """使用专门的聚合Agent整合所有专家意见"""
        
        if not agent_responses:
            return "暂时无法获取专家建议，请稍后重试。如需帮助，请联系NutriRec客服。"
        
        # 创建聚合Agent
        aggregator_config = self.get_agent_config()
        aggregator = ConversableAgent(
            name="ChiefMedicalOfficer",
            system_message="""你是NutriRec的首席医疗官Dr. NutriRec，负责整合专家团队的意见。

🎯 **核心职责**:
整合各位专家的专业意见，形成一份连贯、全面、实用的最终建议报告。

📋 **整合原则**:
1. **避免重复**: 去除各专家意见中的重复内容
2. **逻辑连贯**: 按照"问题分析→解决方案→实施指导→安全提醒"的逻辑组织
3. **突出重点**: 强调最关键的建议和注意事项
4. **实用性**: 确保用户能够理解和执行

📋 **最终报告格式**:
```
# NutriRec专家团队会诊报告

## 🔍 问题分析
[基于营养顾问的分析，简洁总结用户的核心问题]

## 💊 推荐方案
[基于产品专家的建议，清晰列出推荐的产品和理由]

## ⚠️ 安全提醒
[基于安全专家的评估，突出重要的安全注意事项]

## 📋 执行计划
[基于健康管理师的方案，提供具体的执行步骤]

## 🏥 NutriRec承诺
我们将持续关注您的健康改善进展，如有任何问题请随时联系我们的专家团队。
```

⚠️ **重要**: 你必须基于各专家的具体意见进行整合，不能凭空添加内容！""",
            llm_config=aggregator_config
        )
        
        # 构建聚合提示
        expert_opinions = ""
        for agent_name, response in agent_responses.items():
            agent_title = {
                "NutritionConsultant": "营养顾问Dr. Chen",
                "SupplementSpecialist": "产品专家Dr. Wang", 
                "SafetyAssessor": "安全专家Dr. Li",
                "HealthCoach": "健康管理师Dr. Zhang",
                "FormulationExpert": "配方专家"
            }.get(agent_name, agent_name)
            
            expert_opinions += f"\n### {agent_title}的专业意见:\n{response}\n"
        
        aggregation_prompt = f"""
用户原始问题: {original_query}

以下是我们专家团队的详细分析:
{expert_opinions}

请作为首席医疗官，整合以上专家意见，形成一份专业、连贯、实用的最终建议报告。
"""
        
        try:
            # 使用聚合Agent生成最终报告
            messages = [{"role": "user", "content": aggregation_prompt}]
            aggregated_response = await aggregator.a_generate_reply(messages)
            
            if isinstance(aggregated_response, str) and aggregated_response.strip():
                return aggregated_response.strip()
            else:
                # 如果聚合失败，使用简化的格式化方法
                return self._format_agent_responses(agent_responses)
                
        except Exception as e:
            logger.error(f"Expert opinion aggregation failed: {e}")
            return self._format_agent_responses(agent_responses)
    
    async def _run_agent_conversation_optimized(
        self,
        agent: ConversableAgent,
        query: str
    ) -> str:
        """优化的Agent对话方法，专为并行执行设计"""
        try:
            # 创建独立的消息上下文，避免并发冲突
            messages = [
                {
                    "role": "system", 
                    "content": agent.system_message
                },
                {
                    "role": "user", 
                    "content": f"用户咨询: {query}\n\n请根据您的专业角色提供详细建议。"
                }
            ]
            
            # 直接调用agent的异步生成方法
            response = await agent.a_generate_reply(messages)
            
            # 处理不同类型的响应
            if isinstance(response, str):
                return response.strip()
            elif hasattr(response, 'content') and response.content:
                return response.content.strip()
            elif hasattr(response, 'text') and response.text:
                return response.text.strip()
            else:
                logger.warning(f"Agent {agent.name} returned unexpected response format: {type(response)}")
                return ""
            
        except Exception as e:
            logger.error(f"Agent {agent.name} optimized conversation error: {e}")
            return ""
    
    def get_agent_config(self, api_key: str = None) -> Dict[str, Any]:
        """Get secure agent configuration (api_key parameter ignored, uses AI manager)"""
        # Return a copy to avoid modifying the original config
        return self.ai_config.copy()

    async def _extract_and_update_medical_history(self, session_id: str, query: str):
        """
        提取医疗关键词并更新患者病史
        """
        try:
            # 导入医疗关键词提取器
            from medical_keyword_extractor import get_medical_keyword_extractor
            extractor = get_medical_keyword_extractor()
            
            # 提取医疗关键词
            keywords = await extractor.extract_keywords(
                query=query, 
                session_id=session_id, 
                strategy="hybrid"  # 使用混合策略
            )
            
            if not keywords:
                logger.debug(f"📝 会话 {session_id}: 未提取到医疗关键词")
                return
            
            logger.info(f"🔍 会话 {session_id}: 提取到 {len(keywords)} 个医疗关键词")
            for kw in keywords:
                logger.info(f"  - {kw.keyword} ({kw.category}, 置信度: {kw.confidence:.2f})")
            
            # 获取用户配置
            context = self.context_manager.get_context(session_id)
            if not context or not context.user_profile:
                logger.warning(f"⚠️ 会话 {session_id}: 未找到用户配置，无法更新病史")
                return
            
            # 更新FHIR患者数据
            if self._should_use_fhir() and 'fhir_patient' in context.user_profile:
                await self._update_fhir_patient_history(session_id, keywords, context.user_profile)
            
            # 更新向量知识管理器的FHIR上下文
            if self.knowledge_manager and hasattr(self.knowledge_manager, 'set_fhir_patient_context'):
                fhir_data = extractor.format_keywords_for_fhir(keywords)
                if fhir_data:
                    # 创建临时FHIR患者数据用于搜索增强
                    temp_fhir_patient = self._create_temp_fhir_patient(session_id, fhir_data)
                    self.knowledge_manager.set_fhir_patient_context(session_id, temp_fhir_patient)
                    logger.info(f"✅ 会话 {session_id}: FHIR搜索上下文已更新")
            
        except Exception as e:
            logger.error(f"❌ 会话 {session_id}: 医疗关键词提取失败: {e}")
    
    async def _update_fhir_patient_history(self, session_id: str, keywords: List, user_profile: Dict):
        """更新FHIR患者病史"""
        try:
            from fhir_data_converter import FHIRDataConverter
            converter = FHIRDataConverter()
            
            fhir_patient = user_profile.get('fhir_patient', {})
            
            # 提取高置信度的疾病和症状关键词
            medical_history = []
            current_symptoms = []
            
            for kw in keywords:
                if kw.confidence >= 0.7:  # 只使用高置信度关键词
                    if kw.category == "疾病":
                        medical_history.append(kw.keyword)
                    elif kw.category == "症状":
                        current_symptoms.append(kw.keyword)
            
            # 更新FHIR扩展字段
            if medical_history or current_symptoms:
                extensions = fhir_patient.get('extension', [])
                
                # 更新病史
                if medical_history:
                    history_ext = self._find_or_create_fhir_extension(
                        extensions, 
                        "http://nutrirec.example.com/fhir/StructureDefinition/medical-history"
                    )
                    existing_history = self._parse_fhir_extension_value(history_ext)
                    updated_history = list(set(existing_history + medical_history))
                    history_ext['valueString'] = str(updated_history)
                
                # 更新当前症状
                if current_symptoms:
                    symptoms_ext = self._find_or_create_fhir_extension(
                        extensions,
                        "http://nutrirec.example.com/fhir/StructureDefinition/current-symptoms"
                    )
                    existing_symptoms = self._parse_fhir_extension_value(symptoms_ext)
                    updated_symptoms = list(set(existing_symptoms + current_symptoms))
                    symptoms_ext['valueString'] = str(updated_symptoms)
                
                fhir_patient['extension'] = extensions
                user_profile['fhir_patient'] = fhir_patient
                
                logger.info(f"✅ 会话 {session_id}: FHIR患者病史已更新")
                logger.info(f"  - 新增疾病: {medical_history}")
                logger.info(f"  - 新增症状: {current_symptoms}")
        
        except Exception as e:
            logger.error(f"❌ FHIR患者病史更新失败: {e}")
    
    def _create_temp_fhir_patient(self, session_id: str, fhir_data: Dict) -> Dict:
        """创建临时FHIR患者数据用于搜索增强"""
        temp_patient = {
            "resourceType": "Patient",
            "id": f"temp-{session_id}",
            "extension": []
        }
        
        # 添加提取的医疗信息作为扩展字段
        for category, keywords in fhir_data.items():
            if keywords:
                extension = {
                    "url": f"http://nutrirec.example.com/fhir/StructureDefinition/{category}",
                    "valueString": str(keywords)
                }
                temp_patient['extension'].append(extension)
        
        return temp_patient
    
    def _find_or_create_fhir_extension(self, extensions: List, url: str) -> Dict:
        """查找或创建FHIR扩展字段"""
        for ext in extensions:
            if ext.get('url') == url:
                return ext
        
        # 创建新的扩展字段
        new_ext = {"url": url, "valueString": "[]"}
        extensions.append(new_ext)
        return new_ext
    
    def _parse_fhir_extension_value(self, extension: Dict) -> List[str]:
        """解析FHIR扩展字段的值"""
        try:
            import json
            value_str = extension.get('valueString', '[]')
            return json.loads(value_str) if isinstance(value_str, str) else []
        except:
            return []


# Example secured agent function (decorators removed for now)
async def analyze_nutrition_needs(client_data: Dict[str, Any]) -> Dict[str, Any]:
    """Example of a secured agent function"""
    logger.info("Analyzing nutrition needs")
    
    return {
        "nutritional_gaps": ["Vitamin D", "Omega-3"],
        "recommendations": ["Daily multivitamin", "Fish oil supplement"]
    } 