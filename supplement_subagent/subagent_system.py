#!/usr/bin/env python3
"""
NutriRec保健品推荐SubAgent系统
实现基于纯文本知识注入的多专家并发咨询架构

支持动态API配置，可调用：
- OpenAI (GPT-4, GPT-3.5等)
- DeepSeek (deepseek-chat, deepseek-r1等)  
- Claude (Anthropic)
- Grok (xAI)
- Gemini (Google)
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any
import os

logger = logging.getLogger(__name__)

# NutriRecSubAgentSystem class是整个系统的核心，负责调用各个专家的API，并整合专家的分析结果，输出最终的保健品推荐报告。
# 调用格式：
# system = NutriRecSubAgentSystem()
# result = await system.process_consultation(
#     user_input: str,
#     provider: str = "deepseek",
#     model_name: str = "deepseek-chat", 
#     api_key: str = "",
#     base_url: Optional[str] = None,
#     max_tokens: int = 8000,
#     temperature: float = 0.7,
#     timeout: int = 60,
#     max_workers: int = 6
# )
@dataclass
class APIConfig:
    """API配置数据结构"""
    provider: str  # openai, deepseek, claude, grok, gemini
    model_name: str
    api_key: str
    base_url: Optional[str] = None
    max_tokens: int = 8000
    temperature: float = 0.7
    timeout: int = 60
    max_workers: int = 6

@dataclass
class SubAgentResult:
    """SubAgent结果数据结构"""
    agent_name: str
    agent_type: str
    content: str
    processing_time: float

class SubAgentOrchestrator:
    """SubAgent编排器"""
    
    def __init__(self, api_config: APIConfig):
        self.api_config = api_config
        self.executor = ThreadPoolExecutor(max_workers=api_config.max_workers)
        self._setup_client()
        
    def _setup_client(self):
        """根据配置设置API客户端"""
        if self.api_config.provider.lower() == 'openai':
            from openai import OpenAI
            self.client = OpenAI(
                api_key=self.api_config.api_key,
                base_url=self.api_config.base_url
            )
        elif self.api_config.provider.lower() == 'deepseek':
            from openai import OpenAI  # DeepSeek使用OpenAI兼容接口
            self.client = OpenAI(
                api_key=self.api_config.api_key,
                base_url=self.api_config.base_url or 'https://api.deepseek.com'
            )
        elif self.api_config.provider.lower() == 'claude':
            try:
                import anthropic
                self.client = anthropic.Anthropic(
                    api_key=self.api_config.api_key,
                    base_url=self.api_config.base_url
                )
            except ImportError:
                raise ImportError("请安装anthropic库: pip install anthropic")
        elif self.api_config.provider.lower() == 'grok':
            from openai import OpenAI  # Grok使用OpenAI兼容接口
            self.client = OpenAI(
                api_key=self.api_config.api_key,
                base_url=self.api_config.base_url or 'https://api.x.ai/v1'
            )
        elif self.api_config.provider.lower() == 'gemini':
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_config.api_key)
                self.client = genai.GenerativeModel(self.api_config.model_name)
            except ImportError:
                raise ImportError("请安装google-generativeai库: pip install google-generativeai")
        else:
            raise ValueError(f"不支持的API提供商: {self.api_config.provider}")
        
    async def call_api(self, system_prompt: str, user_input: str, is_summary_expert: bool = False) -> str:
        """调用API"""
        try:
            # 根据专家类型调整参数
            max_tokens = min(self.api_config.max_tokens, 8000 if is_summary_expert else 6000)
            timeout = self.api_config.timeout + (30 if is_summary_expert else 0)
            
            if self.api_config.provider.lower() in ['openai', 'deepseek', 'grok']:
                return await self._call_openai_compatible_api(system_prompt, user_input, max_tokens, timeout)
            elif self.api_config.provider.lower() == 'claude':
                return await self._call_claude_api(system_prompt, user_input, max_tokens, timeout)
            elif self.api_config.provider.lower() == 'gemini':
                return await self._call_gemini_api(system_prompt, user_input, max_tokens, timeout)
            else:
                raise ValueError(f"不支持的API提供商: {self.api_config.provider}")
                
        except Exception as e:
            error_msg = str(e)
            logger.error(f"{self.api_config.provider} API调用失败 ({'总结专家' if is_summary_expert else '普通专家'}): {error_msg}")
            return self._format_error_message(error_msg)
    
    async def _call_openai_compatible_api(self, system_prompt: str, user_input: str, max_tokens: int, timeout: int) -> str:
        """调用OpenAI兼容的API (OpenAI, DeepSeek, Grok)"""
        # DeepSeek特殊处理token限制
        if self.api_config.provider.lower() == 'deepseek' and max_tokens > 8192:
            max_tokens = 8192
            
        response = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            lambda: self.client.chat.completions.create(
                model=self.api_config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=self.api_config.temperature,
                max_tokens=max_tokens,
                timeout=timeout
            )
        )
        
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            return "API调用失败: 无有效响应内容"
    
    async def _call_claude_api(self, system_prompt: str, user_input: str, max_tokens: int, timeout: int) -> str:
        """调用Claude API"""
        response = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            lambda: self.client.messages.create(
                model=self.api_config.model_name,
                max_tokens=max_tokens,
                temperature=self.api_config.temperature,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_input}
                ]
            )
        )
        
        if response.content and len(response.content) > 0:
            content = response.content[0].text if hasattr(response.content[0], 'text') else str(response.content[0])
            return content.strip()
        else:
            return "API调用失败: 无有效响应内容"
    
    async def _call_gemini_api(self, system_prompt: str, user_input: str, max_tokens: int, timeout: int) -> str:
        """调用Gemini API"""
        # Gemini不支持system role，需要合并提示
        combined_prompt = f"系统指令: {system_prompt}\n\n用户输入: {user_input}"
        
        generation_config = {
            'temperature': self.api_config.temperature,
            'max_output_tokens': max_tokens,
        }
        
        response = await asyncio.get_event_loop().run_in_executor(
            self.executor,
            lambda: self.client.generate_content(
                combined_prompt,
                generation_config=generation_config
            )
        )
        
        if response.text:
            return response.text.strip()
        else:
            # 检查是否被安全过滤器阻止
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                if response.prompt_feedback.block_reason:
                    return f"内容被Gemini安全过滤器阻止: {response.prompt_feedback.block_reason}"
            return "API调用失败: 无有效响应内容"
    
    def _format_error_message(self, error_msg: str) -> str:
        """格式化错误信息"""
        if "connection" in error_msg.lower():
            return "API调用失败: 网络连接问题，请检查网络设置或稍后重试"
        elif "authentication" in error_msg.lower() or "unauthorized" in error_msg.lower():
            return "API调用失败: API Key无效或已过期，请检查配置"
        elif "quota" in error_msg.lower() or "rate_limit" in error_msg.lower():
            return "API调用失败: API配额不足或请求频率过高，请稍后重试"
        elif "context_length" in error_msg.lower() or "token" in error_msg.lower():
            return "API调用失败: 输入内容过长，请简化查询或分批处理"
        elif "Invalid max_tokens value" in error_msg:
            return "API调用失败: token数量超过限制，请减少输入长度"
        elif "Model Not Exist" in error_msg:
            return "API调用失败: 模型不存在，请检查模型名称"
        else:
            return f"API调用失败: {error_msg}"

    def get_demand_analysis_expert_prompt(self) -> str:
        """获取需求分析专家的系统提示词"""
        return """你是NutriRec的需求分析专家Dr. Analysis，专精用户需求深度解析和澄清点识别。

**专业职责**:
1. 深入分析用户健康目标、症状、偏好和背景信息
2. 识别用户需求中的显式和隐式要求
3. 从输入中匹配相关的合作商城产品和合作门诊信息
4. 识别需要澄清的关键信息点，确保推荐的准确性

**负责报告模板部分**: 你负责填充最终报告的"## 营养需求分析"部分。该部分的模板结构如下：
  - **需求描述**：深入解析用户健康目标、症状、偏好、背景和澄清点。从查询和知识库提取显式/隐式需求，详细解释每个类别的影响（如目标如何链接到生长发育）。匹配supplement标签/功效（如"挑食"匹配"免疫力低下"）和clinics服务（如"儿童保健"）。如果模糊，列出多个澄清点并解释理由（e.g., 年龄影响用量）。
  - **格式要求**：使用无序列表（-）分类别，每个类别下添加子弹点解释细节和匹配知识。
  - **示例**：
    - **核心目标**：提升免疫力和促进生长发育。子目标包括改善挑食导致的营养吸收不良，基于知识库匹配"长高""免疫力低下"标签的产品功效，如锌补充可增强食欲。
    - **症状与背景**：症状：挑食、可能免疫低下（频率：日常）；背景：3岁儿童，幼儿阶段易营养缺乏，无指定性别/生活方式，无指定城市，影响门诊匹配，建议澄清所在地。
    - **偏好**：未指定，但适合儿童口感佳的产品（如滴剂）。
    - **澄清点**：未指定过敏史，可能风险高，建议询问以避免互动；未提城市，影响门诊匹配，建议澄清所在地。
    - **匹配知识**：supplement："童年故事锌牡蛎橙复合饮液"（标签：挑食、生长发育缓慢，功效：增强免疫）；clinics："丽晶门诊部"（服务：儿童生长发育，地址：广州市天河区金穗路28号）。

**输出要求**: 严格按照以下JSON结构输出，不要添加任何其他文本

{
  "demands": [
    {
      "category": "核心目标",
      "details": "用户的主要健康目标和期望效果",
      "knowledge_match": "从知识库匹配的相关标签或功效"
    },
    {
      "category": "症状与背景", 
      "details": "具体症状描述和影响",
      "frequency": "症状频率或严重程度",
      "context": "年龄、性别、生活方式等背景信息"
    },
    {
      "category": "偏好",
      "details": "用户的产品偏好、口感要求、成分偏好等"
    },
    {
      "category": "澄清点",
      "details": "需要进一步澄清的关键信息",
      "reason": "为什么这个信息很重要"
    }
  ],
  "matched_knowledge": {
    "supplements": ["从知识库匹配的具体产品名称和标签"],
    "clinics": ["从知识库匹配的门诊名称和服务"]
  }
}

请仔细分析输入的用户查询、知识库信息，输出完整准确的JSON结构"""
    
    def get_nutrition_science_expert_prompt(self) -> str:
        """获取营养科学专家的系统提示词"""
        return """你是NutriRec的营养科学专家Dr. Science，拥有营养学博士学位和15年临床研究经验。

**专业职责**:
1. 评估至少3-5个关键营养素的健康益处，每项包括详细作用机制、量化益处（如"提升吸收率30%"）和适用场景分析
2. 深入分析营养素的协同作用（至少3-4个组合示例）和吸收优化方案（至少3-4个方法）
3. 提供病理机制解析：分析用户症状的营养学病理基础，解释营养缺乏如何导致当前问题，包括生理通路和分子机制
4. 计算精确的营养素推荐用量，至少3-4个营养素，每项基于年龄/性别/需求分级并解释计算依据

**负责报告模板部分**: 你负责填充最终报告的"## 营养益处与科学解析"部分。该部分的模板结构如下：
  - **需求描述**：详细评估关键营养素的益处、成分分析和科学依据。解释机制、量化益处、用量建议和证据来源（检索中studies或一般知识）。链接合作门诊服务（如营养管理门诊细节，包括地址/电话）。覆盖短期/长期效果和协同作用。
  - **格式要求**：使用有序列表（1.）或表格列出营养素；每个下添加段落解释。
  - **示例**：
    - **锌的益处**：支持免疫功能和伤口愈合，机制：促进T细胞活性，证据：研究显示补锌可减少感冒频率20%。针对挑食儿童，改善食欲。
    - **维生素D的益处**：促进钙吸收和骨骼发育，机制：激活维生素D受体，证据：基于检索"童年故事维生素D3片"（标签：长高），每日1片可提升发育。
    - **成分分析**：锌牡蛎橙复合饮液：每0.5ml含锌，协同维生素C提升吸收；用量：0.5ml/天，避免过量。
    - **整体总结**：这些营养针对儿童需求，建议结合"儿童康复中心"营养管理（地址：广州市天河区金穗路28号，电话：020-89811485）。
    - **科学证据**：1. Zinc study (PMID:12345)；2. Vitamin D from NIH guidelines。

**输出要求**: 严格按照以下JSON结构输出，不要添加任何其他文本

{
  "benefits": [
    {
      "nutrient": "具体营养素名称",
      "mechanism": "作用机制的科学解释", 
      "evidence": "支持的科学研究或临床证据",
      "dosage": "基于年龄和需求的推荐每日用量"
    }
  ],
  "analysis": {
    "key_nutrients": ["针对用户需求的关键营养素列表"],
    "synergy": "营养素之间的协同作用分析",
    "absorption": "提高吸收率的建议和最佳服用时间"
  },
  "scientific_evidence": [
    {
      "source": "研究来源或权威机构",
      "finding": "具体的研究发现或结论", 
      "relevance": "与用户具体需求的关联性说明"
    }
  ],
  "pathological_analysis": {
    "symptom_mechanism": "用户症状的病理学机制解析",
    "nutritional_pathway": "营养缺乏导致症状的生理通路",
    "molecular_basis": "分子水平的作用机制说明"
  }
}

基于最新营养学研究提供科学准确的分析"""
    
    def get_product_matching_expert_prompt(self) -> str:
        """获取产品匹配专家的系统提示词"""
        return """你是NutriRec的产品匹配专家Dr. Matcher，负责从输入中提取和整理所有产品及门诊信息。

**专业职责**:
1. **需求匹配分析**：首先分析用户的核心健康需求和症状
2. **产品相关性判断**：仅提取与用户需求直接相关的【产品】信息
   - 检查产品功效与用户症状的匹配度
   - 检查产品适用人群与用户情况的符合度
   - 如果产品功效与用户需求不相关，则不提取该产品
3. **门诊信息提取**：提取所有【诊所】/【门诊】信息，包含完整的服务细节
4. **信息整理**：整理匹配产品的完整信息和门诊信息

**相关性判断标准**:
- 产品功效必须直接针对用户的症状或健康目标
- 产品适用人群必须与用户年龄、性别、健康状况相符
- 严格排除不相关产品（如：失眠患者不推荐备孕产品，儿童不推荐成人产品）

**重要提醒**:
- 只提取与用户需求高度相关的产品，宁可缺少也不要不相关
- 必须包含每个相关产品的所有可用信息字段
- 必须包含每个门诊的所有详细信息，特别是停车券、完整电话等

**输出要求**: 严格按照以下JSON结构输出，不要添加任何其他文本

{
  "matches": [
    {
      "category": "产品分类",
      "name": "完整产品名称",
      "effectiveness": "主要功效和作用机制", 
      "ingredients": "主要成分列表",
      "usage": "详细用法用量",
      "link": "购买链接",
      "restrictions": "注意事项和限制",
      "rationale": "针对用户需求的推荐理由"
    }
  ],
  "clinics": [
    {
      "name": "门诊名称",
      "address": "详细地址", 
      "phone": "完整联系电话（包括分机）",
      "hours": "营业时间",
      "services": "详细服务内容",
      "parking": "停车信息（免费停车券等）"
    }
  ],
  "similar_products": ["其他相关产品名称"]
}

**相关性判断示例**:
- ✅ 用户失眠 + 产品含褪黑素/镁 → 相关，提取
- ❌ 用户失眠 + 备孕产品 → 不相关，不提取  
- ✅ 用户儿童注意力 + 儿童营养品 → 相关，提取
- ❌ 用户儿童注意力 + 成人保健品 → 不相关，不提取

务必严格按照相关性标准筛选产品，确保推荐的准确性"""
    
    def get_risk_assessment_expert_prompt(self) -> str:
        """获取风险评估专家的系统提示词"""
        return """你是NutriRec的风险评估专家Dr. Risk，专注健康安全评估和病理分析。

**专业职责**:
1. 综合评估用户健康状况，给出一个主要的风险判断（高/中/低）
2. 深入解析该风险的病理机制、发生概率和具体症状表现
3. 分析症状背后的生理机制和长期影响
4. 提供详细的风险缓解措施和监测建议
5. 识别产品禁忌症和注意事项

**重要说明**:
- 重点是给出一个综合性的主要风险评估，而不是多个分散的风险点
- 风险解析要深入具体，包含病理机制和缓解方案
- 监测建议要实用可操作

**输出要求**: 严格按照以下JSON结构输出，不要添加任何其他文本

{
  "primary_risk": {
    "level": "高/中/低", 
    "description": "主要风险的综合描述",
    "mechanism": "详细的病理机制解析，包括生理通路和分子基础",
    "probability": "发生概率和影响程度评估",
    "symptoms": "可能出现的具体症状表现"
  },
  "risk_analysis": {
    "pathological_basis": "症状的病理学基础和生理机制分析",
    "contributing_factors": "加重风险的相关因素",
    "long_term_consequences": "长期不处理的潜在后果"
  },
  "mitigation_strategies": {
    "immediate_measures": "立即可采取的缓解措施",
    "monitoring_plan": "建议的监测指标和频率",
    "lifestyle_adjustments": "生活方式调整建议",
    "medical_consultation": "需要的医疗咨询和门诊建议"
  },
  "product_safety": {
    "contraindications": "产品使用的禁忌症",
    "dosage_warnings": "剂量相关的安全提醒",
    "interaction_risks": "可能的药物或食物相互作用"
  },
  "overall_assessment": "综合安全性评估和总体建议"
}

提供全面深入的单一风险评估，确保用户健康安全"""
    
    def get_summary_expert_prompt(self, expert_results: List[SubAgentResult], query: str) -> str:
        """获取总结专家的系统提示词"""
        current_date = datetime.now().strftime("%Y年%m月%d日")

        # 提取各专家的JSON输出
        demand_analysis = ""
        nutrition_science = ""
        product_matching = ""
        risk_assessment = ""
        
        for result in expert_results:
            if result.agent_name == "DemandAnalysisExpert":
                demand_analysis = result.content
            elif result.agent_name == "NutritionScienceExpert":
                nutrition_science = result.content  
            elif result.agent_name == "ProductMatchingExpert":
                product_matching = result.content
            elif result.agent_name == "RiskAssessmentExpert":
                risk_assessment = result.content

        
        return f"""你是NutriRec的总结专家Dr. Summary，负责将四位专家的JSON分析整合为用户友好的保健品推荐报告。

**核心任务**：
1. **信息提取**：从四位专家的JSON中提取核心信息
2. **格式整理**：按markdown模板组织，保持简洁清晰  
3. **用户友好**：使用通俗易懂的语言表达

**专家输出**：
需求分析：{demand_analysis}
营养科学：{nutrition_science}  
产品匹配：{product_matching}
风险评估：{risk_assessment}

**用户问题**：{query}

**输出格式**：严格按以下markdown结构输出，每个部分都要完成相应任务

# 保健品推荐分析报告（{current_date}）

## 需求分析与营养解析
任务：结合需求分析专家和营养科学专家的分析，为客户提供易懂的解释：
1. **健康目标**：用户的主要健康目标和期望改善的症状
2. **症状原因**：从营养学角度解释症状产生的可能原因（如营养缺乏、代谢问题等）
3. **营养需求**：基于症状分析，说明身体当前最需要哪些营养支持
4. **个人情况**：考虑用户的年龄、性别、生活习惯等个体化因素

## 营养建议  
任务：从营养科学专家的benefits和analysis中整理，用通俗易懂的语言解释：

**营养补充原理**：首先用1-2句话解释为什么需要这些营养素，它们如何帮助改善用户的症状

**具体营养方案**：
1. **关键营养素**：列出3-4个营养素，每个包含：
   - 营养素名称和简单作用原理  
   - 对用户症状的具体帮助
   - 推荐用量和科学依据
2. **协同作用**：用简单语言解释营养素之间如何相互增强效果
3. **服用建议**：最佳服用时间、方法和注意事项

## 推荐产品
任务：从产品匹配专家的matches数组中生成表格：
| 产品名称 | 主要功效 | 用法用量 | 购买链接 | 注意事项 |
- 确保每行对应matches数组中的一个产品，只推荐与用户需求相关的，如果没有匹配的产品则回复"抱歉，合作商城暂时没有类似的产品，您可以根据报告浏览其他产品。"
- 如果matches数组为空但输入中有产品信息，则根据其他专家分析推断产品信息

## 风险提醒
任务：从风险评估专家的分析中提取，用客户易懂的语言解释：
1. **风险等级**：主要风险的等级和综合描述（来自primary_risk）
2. **风险原因**：用通俗语言解释为什么会产生这些风险（来自risk_analysis）
3. **预防措施**：
   - 立即可做的事情：具体的行动建议
   - 生活调整：日常习惯的改善建议  
   - 定期监测：需要关注的身体指标
4. **产品使用安全**：详细解释产品安全注意事项，包括：
   - 哪些人不能使用（禁忌人群）
   - 为什么不能使用（风险机制的通俗解释）
   - 用量控制的重要性（过量风险的简单说明）
   - 与其他药物或食物的相互作用（具体后果说明）

## 就诊建议
任务：从产品匹配专家的clinics数组中用表格形式列出完整门诊信息：
| 门诊名称 | 地址 | 电话 | 营业时间 | 核心服务 | 停车信息 |
- 必须包含所有门诊的完整信息，特别是停车券、分机电话等详细信息
- 电话栏显示完整联系方式，营业时间包含休息日说明

## 行动步骤
任务：直接提供4步行动指南：
1. 产品购买：可以通过提供的商品链接直接购买
2. 使用指导：按推荐用量服用，注意禁忌
3. 门诊预约：可尝试直接跟我说"我想要预约门诊"，NutriRec助手会帮您匹配到合适的医生
4. 后续咨询：有问题可继续咨询或回复"人工"转客服

**免责声明**：本建议仅供参考，不构成医疗诊断也不代表NutriRec的官方立场，请在医生指导下使用。

**具体要求**：
1. **数据使用**：直接引用专家JSON中的具体数据，不要重复扩展或推测
2. **产品完整性**：必须显示所有产品，即使产品匹配专家的matches为空也要根据其他信息补充
3. **风险结构**：使用风险评估专家的新JSON结构（primary_risk、risk_analysis、mitigation_strategies、product_safety）
4. **门诊详细性**：门诊表格必须包含停车信息、完整电话等所有可用详细信息
5. **长度控制**：总长度控制在1500-2000字，确保信息详细易懂
6. **信息完整**：必须包含产品推荐、风险提醒、门诊信息、使用指导四大要素
7. **语言风格**：自然流畅，避免专业术语，多使用类比和通俗解释，让普通客户容易理解
8. **格式规范**：严格按照markdown模板结构，使用表格和列表增强可读性

仅输出markdown报告，无其他文本。"""
    
    async def process_expert_consultation(self, system_prompt: str, user_input: str, agent_name: str, agent_type: str, is_summary_expert: bool = False) -> SubAgentResult:
        """处理单个专家咨询"""
        start_time = time.time()
        
        try:
            response = await self.call_api(system_prompt, user_input, is_summary_expert)
            processing_time = time.time() - start_time
            
            return SubAgentResult(
                agent_name=agent_name,
                agent_type=agent_type,
                content=response,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"专家 {agent_name} 处理失败: {e}")
            return SubAgentResult(
                agent_name=agent_name,
                agent_type=agent_type,
                content=f"专家 {agent_type} 暂时无法提供建议，请稍后重试。",
                processing_time=time.time() - start_time
            )
    
    async def execute_parallel_consultation(self, user_input: str) -> Dict[str, Any]:
        """执行并行专家咨询 - 输入已包含所有需要的信息"""
        try:
            start_time = time.time()
            logger.info(f"🚀 开始并行专家咨询...")
            
            # 并发执行四大专家咨询
            logger.info("⚡ 并发执行专家咨询...")
            expert_tasks = [
                self.process_expert_consultation(
                    self.get_demand_analysis_expert_prompt(), 
                    user_input, 
                    "DemandAnalysisExpert", 
                    "需求分析专家"
                ),
                self.process_expert_consultation(
                    self.get_nutrition_science_expert_prompt(), 
                    user_input, 
                    "NutritionScienceExpert", 
                    "营养科学专家"
                ),
                self.process_expert_consultation(
                    self.get_product_matching_expert_prompt(), 
                    user_input, 
                    "ProductMatchingExpert", 
                    "产品匹配专家"
                ),
                self.process_expert_consultation(
                    self.get_risk_assessment_expert_prompt(), 
                    user_input, 
                    "RiskAssessmentExpert", 
                    "风险评估专家"
                )
            ]
            
            expert_results = await asyncio.gather(*expert_tasks)
            
            # 整合专家意见 - 使用更强的模型
            logger.info("🎯 整合专家意见...")
            summary_prompt = self.get_summary_expert_prompt(expert_results, user_input)
            
            # 简化输入给总结专家，避免token超限
            simplified_input = "请基于以上专家JSON输出，按照模板生成完整的保健品推荐分析报告"
            
            final_result = await self.process_expert_consultation(
                summary_prompt, 
                simplified_input, 
                "SummaryExpert", 
                "总结专家",
                is_summary_expert=True  # 标记为总结专家
            )
            
            total_time = time.time() - start_time
            
            logger.info(f"✅ 并行咨询完成，总耗时: {total_time:.2f}s")
            
            return {
                "status": "success",
                "expert_results": [
                    {
                        "agent_name": result.agent_name,
                        "agent_type": result.agent_type,
                        "content": result.content,
                        "processing_time": result.processing_time
                    }
                    for result in expert_results
                ],
                "final_recommendation": final_result.content,
                "total_processing_time": total_time,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"并行咨询执行失败: {e}")
            return {
                "status": "error",
                "message": f"专家咨询系统暂时不可用: {str(e)}"
            }

class NutriRecSubAgentSystem:
    """NutriRecSubAgent系统主类"""
    
    def __init__(self):
        self.orchestrator = None
        logger.info("✅ NutriRecSubAgent系统初始化完成")
    
    async def process_consultation(
        self, 
        user_input: str, # 用户输入
        provider: str = "deepseek", # 提供商
        model_name: str = "deepseek-chat", # 模型名称
        api_key: str = "", # API密钥
        base_url: Optional[str] = None, # API基础URL
        max_tokens: int = 8000, # 最大token数
        temperature: float = 0.7, # 温度参数
        timeout: int = 60, # 超时时间（秒）
        max_workers: int = 6 # 并行工作线程数
    ) -> Dict[str, Any]:
        """
        处理用户咨询 - 支持动态API配置
        
        Args:
            user_input: 用户输入（已包含所有需要的信息）
            provider: API提供商 (openai/deepseek/claude/grok/gemini)
            model_name: 模型名称
            api_key: API密钥
            base_url: API基础URL（可选）
            max_tokens: 最大token数
            temperature: 温度参数
            timeout: 超时时间（秒）
            max_workers: 并行工作线程数
            
        Returns:
            咨询结果字典
        """
        try:
            # 验证必要参数
            if not user_input:
                return {
                    "status": "error",
                    "message": "用户输入不能为空"
                }
            
            if not api_key:
                return {
                    "status": "error", 
                    "message": "API密钥不能为空"
                }
            
            # 创建API配置
            api_config = APIConfig(
                provider=provider,
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                max_workers=max_workers
            )
            
            # 创建编排器
            self.orchestrator = SubAgentOrchestrator(api_config)
            
            logger.info(f"🔧 使用API配置: {provider}/{model_name}")
            
            # 执行并行专家咨询
            result = await self.orchestrator.execute_parallel_consultation(user_input)
            return result
            
        except Exception as e:
            logger.error(f"咨询处理失败: {e}")
            return {
                "status": "error",
                "message": f"咨询服务暂时不可用: {str(e)}"
            }

    def test_api_connection(
        self,
        provider: str = "deepseek",
        model_name: str = "deepseek-chat", 
        api_key: str = "",
        base_url: Optional[str] = None
    ) -> bool:
        """
        测试API连接
        
        Args:
            provider: API提供商
            model_name: 模型名称
            api_key: API密钥
            base_url: API基础URL（可选）
            
        Returns:
            连接是否成功
        """
        try:
            if not api_key:
                print("❌ API密钥不能为空")
                return False
                
            # 创建临时配置
            api_config = APIConfig(
                provider=provider,
                model_name=model_name,
                api_key=api_key,
                base_url=base_url,
                max_tokens=10,
                timeout=10
            )
            
            # 创建临时编排器
            temp_orchestrator = SubAgentOrchestrator(api_config)
            
            async def _test():
                response = await temp_orchestrator.call_api(
                    "你是一个测试助手。",
                    "请回复'连接成功'"
                )
                return "连接成功" in response or "API调用失败" not in response
            
            result = asyncio.run(_test())
            
            if result:
                print(f"✅ {provider} API 连接成功！")
            else:
                print(f"❌ {provider} API 连接失败")
                
            return result
            
        except Exception as e:
            print(f"❌ API连接测试失败：{str(e)}")
            return False

# 全局实例
_subagent_system = None

def get_subagent_system() -> NutriRecSubAgentSystem:
    """获取SubAgent系统实例（单例模式）"""
    global _subagent_system
    if _subagent_system is None:
        _subagent_system = NutriRecSubAgentSystem()
    return _subagent_system 