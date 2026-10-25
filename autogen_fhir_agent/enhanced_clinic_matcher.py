"""
增强门诊匹配器
提供高级门诊搜索和匹配功能，集成地理位置、对话上下文等智能匹配算法
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import json

logger = logging.getLogger(__name__)

class ClinicMatcherAdapter:
    """
    增强门诊匹配适配器
    为VectorKnowledgeManager提供高级门诊搜索功能
    """
    
    def __init__(self, vector_manager):
        """
        初始化增强门诊匹配器
        
        Args:
            vector_manager: VectorKnowledgeManager实例
        """
        self.vector_manager = vector_manager
        self.logger = logging.getLogger(__name__)
        
        # 门诊相关关键词
        self.clinic_keywords = {
            '科室': ['内科', '外科', '妇科', '儿科', '眼科', '耳鼻喉科', '皮肤科', '骨科', '神经科', '心理科'],
            '症状': ['发烧', '咳嗽', '头痛', '腹痛', '胸痛', '呼吸困难', '恶心', '呕吐', '腹泻', '失眠'],
            '治疗': ['检查', '治疗', '手术', '康复', '体检', '疫苗', '输液', '换药', '复查', '咨询'],
            '地理': ['附近', '就近', '方便', '距离', '交通', '地铁', '公交', '开车', '步行', '周边']
        }
        
        # 城市权重配置
        self.city_weights = {
            '北京': 1.0, '上海': 1.0, '广州': 0.9, '深圳': 0.9,
            '杭州': 0.8, '南京': 0.8, '成都': 0.8, '武汉': 0.8,
            '西安': 0.7, '重庆': 0.7, '天津': 0.7, '苏州': 0.7
        }
        
    async def enhanced_clinic_search_with_context(
        self, 
        query: str, 
        user_city: Optional[str] = None,
        conversation_history: Optional[List[Dict]] = None,
        max_results: int = 10
    ) -> Dict[str, Any]:
        """
        带上下文的增强门诊搜索
        
        Args:
            query: 搜索查询
            user_city: 用户城市
            conversation_history: 对话历史
            max_results: 最大结果数量
            
        Returns:
            增强搜索结果
        """
        try:
            self.logger.info(f"🏥 开始增强门诊搜索: {query[:50]}...")
            
            # 1. 分析查询意图
            intent_analysis = self._analyze_query_intent(query)
            
            # 2. 提取上下文信息
            context_info = self._extract_context_info(conversation_history)
            
            # 3. 地理位置增强
            location_boost = self._calculate_location_boost(query, user_city)
            
            # 4. 执行基础向量搜索
            base_results = await self._perform_base_search(query, max_results * 2)
            
            # 5. 智能重排序
            enhanced_results = self._intelligent_rerank(
                base_results, 
                intent_analysis, 
                context_info, 
                location_boost,
                user_city
            )
            
            # 6. 生成搜索元数据
            search_metadata = self._generate_search_metadata(
                query, intent_analysis, context_info, location_boost
            )
            
            # 7. 格式化最终结果
            final_results = {
                'results': enhanced_results[:max_results],
                'total_found': len(enhanced_results),
                'search_metadata': search_metadata,
                'intent_analysis': intent_analysis,
                'location_info': {
                    'user_city': user_city,
                    'location_boost': location_boost
                }
            }
            
            self.logger.info(f"✅ 增强门诊搜索完成，找到 {len(enhanced_results)} 个结果")
            return final_results
            
        except Exception as e:
            self.logger.error(f"❌ 增强门诊搜索失败: {e}")
            # 回退到基础搜索
            return await self._fallback_search(query, max_results)
    
    def _analyze_query_intent(self, query: str) -> Dict[str, Any]:
        """分析查询意图"""
        intent = {
            'primary_intent': 'general',
            'department_mentioned': [],
            'symptoms_mentioned': [],
            'treatment_mentioned': [],
            'location_mentioned': [],
            'urgency_level': 'normal',
            'confidence': 0.0
        }
        
        query_lower = query.lower()
        
        # 检测科室
        for dept in self.clinic_keywords['科室']:
            if dept in query:
                intent['department_mentioned'].append(dept)
                intent['primary_intent'] = 'department_search'
        
        # 检测症状
        for symptom in self.clinic_keywords['症状']:
            if symptom in query:
                intent['symptoms_mentioned'].append(symptom)
                intent['primary_intent'] = 'symptom_search'
        
        # 检测治疗需求
        for treatment in self.clinic_keywords['治疗']:
            if treatment in query:
                intent['treatment_mentioned'].append(treatment)
        
        # 检测地理位置需求
        for location in self.clinic_keywords['地理']:
            if location in query:
                intent['location_mentioned'].append(location)
        
        # 检测紧急程度
        urgent_keywords = ['急', '紧急', '马上', '立即', '赶紧', '严重']
        if any(keyword in query for keyword in urgent_keywords):
            intent['urgency_level'] = 'urgent'
        
        # 计算置信度
        total_matches = (len(intent['department_mentioned']) + 
                        len(intent['symptoms_mentioned']) + 
                        len(intent['treatment_mentioned']) + 
                        len(intent['location_mentioned']))
        intent['confidence'] = min(total_matches * 0.25, 1.0)
        
        return intent
    
    def _extract_context_info(self, conversation_history: Optional[List[Dict]]) -> Dict[str, Any]:
        """提取对话上下文信息"""
        context = {
            'previous_departments': [],
            'previous_symptoms': [],
            'user_preferences': {},
            'conversation_length': 0
        }
        
        if not conversation_history:
            return context
        
        context['conversation_length'] = len(conversation_history)
        
        # 分析历史对话中的医疗相关信息
        for msg in conversation_history[-5:]:  # 只看最近5条消息
            content = msg.get('content', '').lower()
            
            # 提取之前提到的科室
            for dept in self.clinic_keywords['科室']:
                if dept in content:
                    context['previous_departments'].append(dept)
            
            # 提取之前提到的症状
            for symptom in self.clinic_keywords['症状']:
                if symptom in content:
                    context['previous_symptoms'].append(symptom)
        
        # 去重
        context['previous_departments'] = list(set(context['previous_departments']))
        context['previous_symptoms'] = list(set(context['previous_symptoms']))
        
        return context
    
    def _calculate_location_boost(self, query: str, user_city: Optional[str]) -> Dict[str, float]:
        """计算地理位置权重提升"""
        boost = {
            'city_boost': 1.0,
            'distance_preference': 0.0,
            'location_specificity': 0.0
        }
        
        if user_city:
            # 城市权重
            boost['city_boost'] = self.city_weights.get(user_city, 0.5)
            
            # 距离偏好
            distance_keywords = ['附近', '就近', '方便', '距离近']
            if any(keyword in query for keyword in distance_keywords):
                boost['distance_preference'] = 0.3
            
            # 位置特异性
            if user_city in query:
                boost['location_specificity'] = 0.2
        
        return boost
    
    async def _perform_base_search(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """执行基础向量搜索"""
        try:
            # 调用vector_manager的门诊搜索功能
            if hasattr(self.vector_manager, 'search_nutrirec_clinics'):
                results = await self.vector_manager.search_nutrirec_clinics(
                    query=query,
                    max_results=max_results,
                    session_id="enhanced_search",
                    conversation_context=None
                )
                return results.get('results', [])
            else:
                # 回退到通用搜索
                results = await self.vector_manager.hybrid_search(
                    query=query,
                    sources=['clinics']
                )
                return results[:max_results]
                
        except Exception as e:
            self.logger.warning(f"基础搜索失败: {e}")
            return []
    
    def _intelligent_rerank(
        self, 
        results: List[Dict[str, Any]], 
        intent_analysis: Dict[str, Any],
        context_info: Dict[str, Any],
        location_boost: Dict[str, float],
        user_city: Optional[str]
    ) -> List[Dict[str, Any]]:
        """智能重排序"""
        
        def calculate_relevance_score(result: Dict[str, Any]) -> float:
            score = result.get('score', 0.0)
            
            # 意图匹配加分
            content = result.get('content', '').lower()
            metadata = result.get('metadata', {})
            
            # 科室匹配
            for dept in intent_analysis['department_mentioned']:
                if dept in content:
                    score += 0.2
            
            # 症状匹配
            for symptom in intent_analysis['symptoms_mentioned']:
                if symptom in content:
                    score += 0.15
            
            # 地理位置匹配
            if user_city:
                original_data = metadata.get('original_data', {})
                clinic_city = original_data.get('城市', '')
                if user_city in clinic_city:
                    score += location_boost['city_boost'] * 0.3
                    score += location_boost['distance_preference']
                    score += location_boost['location_specificity']
            
            # 上下文连续性
            for prev_dept in context_info['previous_departments']:
                if prev_dept in content:
                    score += 0.1
            
            # 紧急程度调整
            if intent_analysis['urgency_level'] == 'urgent':
                urgent_keywords = ['急诊', '24小时', '紧急', '随时']
                if any(keyword in content for keyword in urgent_keywords):
                    score += 0.25
            
            return score
        
        # 重新计算分数并排序
        for result in results:
            result['enhanced_score'] = calculate_relevance_score(result)
        
        # 按增强分数排序
        results.sort(key=lambda x: x.get('enhanced_score', 0), reverse=True)
        
        return results
    
    def _generate_search_metadata(
        self, 
        query: str, 
        intent_analysis: Dict[str, Any],
        context_info: Dict[str, Any],
        location_boost: Dict[str, float]
    ) -> Dict[str, Any]:
        """生成搜索元数据"""
        return {
            'search_type': 'enhanced_clinic_search',
            'query_length': len(query),
            'intent_confidence': intent_analysis['confidence'],
            'primary_intent': intent_analysis['primary_intent'],
            'context_available': context_info['conversation_length'] > 0,
            'location_enhanced': location_boost['city_boost'] > 1.0,
            'timestamp': datetime.now().isoformat(),
            'search_features': {
                'department_detection': len(intent_analysis['department_mentioned']) > 0,
                'symptom_detection': len(intent_analysis['symptoms_mentioned']) > 0,
                'location_detection': len(intent_analysis['location_mentioned']) > 0,
                'urgency_detection': intent_analysis['urgency_level'] == 'urgent'
            }
        }
    
    async def _fallback_search(self, query: str, max_results: int) -> Dict[str, Any]:
        """回退搜索方案"""
        try:
            self.logger.info("🔄 使用回退搜索方案")
            
            # 简单的基础搜索
            if hasattr(self.vector_manager, 'search_nutrirec_clinics'):
                results = await self.vector_manager.search_nutrirec_clinics(
                    query=query,
                    max_results=max_results,
                    session_id="fallback_search",
                    conversation_context=None
                )
            else:
                results = {'results': [], 'total_found': 0}
            
            # 添加回退标记
            results['search_metadata'] = {
                'search_type': 'fallback_clinic_search',
                'timestamp': datetime.now().isoformat(),
                'fallback_reason': 'enhanced_search_failed'
            }
            
            return results
            
        except Exception as e:
            self.logger.error(f"❌ 回退搜索也失败: {e}")
            return {
                'results': [],
                'total_found': 0,
                'search_metadata': {
                    'search_type': 'failed_search',
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                }
            }
 