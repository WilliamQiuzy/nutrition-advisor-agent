"""
医疗关键词提取器
从用户查询中提取医疗相关关键词，用于更新患者病史
支持多种提取策略：快速NLP + 智能LLM验证
"""

import re
import logging
import asyncio
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass
import jieba
import jieba.posseg as pseg
from collections import defaultdict

logger = logging.getLogger(__name__)

@dataclass
class MedicalKeyword:
    """医疗关键词数据结构"""
    keyword: str
    category: str  # 症状、疾病、药物、治疗等
    confidence: float  # 置信度 0-1
    source: str  # 提取来源：nlp, llm, rule
    context: str  # 原始上下文

class MedicalKeywordExtractor:
    """医疗关键词提取器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 初始化jieba
        self._init_jieba()
        
        # 医疗词典
        self.medical_dict = self._build_medical_dictionary()
        
        # 症状模式
        self.symptom_patterns = self._build_symptom_patterns()
        
        # LLM配置
        self.use_llm_verification = True
        self.llm_timeout = 5.0  # 5秒超时
        
    def _init_jieba(self):
        """初始化jieba分词器"""
        try:
            # 添加医疗专业词汇
            medical_words = [
                "高血压", "糖尿病", "心脏病", "冠心病", "心肌梗死", "脑梗死", "中风",
                "头痛", "失眠", "胸痛", "腹痛", "咳嗽", "发烧", "恶心", "呕吐",
                "内科", "外科", "妇科", "儿科", "心内科", "神经科", "骨科",
                "阿司匹林", "降压药", "胰岛素", "抗生素", "止痛药",
                "血压高", "血糖高", "心率快", "呼吸困难", "胸闷", "头晕"
            ]
            
            for word in medical_words:
                jieba.add_word(word)
                
            self.logger.info("✅ jieba医疗词典初始化完成")
        except Exception as e:
            self.logger.warning(f"⚠️ jieba初始化失败: {e}")
    
    def _build_medical_dictionary(self) -> Dict[str, List[str]]:
        """构建医疗词典"""
        return {
            "疾病": [
                "高血压", "低血压", "糖尿病", "心脏病", "冠心病", "心肌梗死", 
                "脑梗死", "中风", "癌症", "肿瘤", "肝炎", "肾病", "哮喘",
                "关节炎", "骨质疏松", "甲亢", "甲减", "贫血", "胃炎", "胃溃疡"
            ],
            "症状": [
                "头痛", "头晕", "失眠", "胸痛", "胸闷", "腹痛", "恶心", "呕吐",
                "咳嗽", "发烧", "发热", "乏力", "疲劳", "心悸", "气短", "呼吸困难",
                "便秘", "腹泻", "食欲不振", "体重下降", "水肿", "皮疹", "瘙痒"
            ],
            "药物": [
                "阿司匹林", "降压药", "胰岛素", "抗生素", "止痛药", "感冒药",
                "维生素", "钙片", "鱼油", "蛋白粉", "益生菌", "叶酸", "铁剂"
            ],
            "治疗": [
                "手术", "化疗", "放疗", "理疗", "针灸", "按摩", "康复训练",
                "饮食调理", "运动疗法", "心理治疗", "中医治疗"
            ],
            "检查": [
                "血压", "血糖", "血脂", "心电图", "B超", "CT", "MRI", "X光",
                "血常规", "尿常规", "肝功能", "肾功能", "甲状腺功能"
            ]
        }
    
    def _build_symptom_patterns(self) -> List[str]:
        """构建症状识别模式"""
        return [
            r"(.{0,3})(痛|疼|酸|胀|麻|痒|肿|红|热)",  # 身体部位 + 感觉
            r"(感觉|觉得|有点|有些|经常|总是|最近)(.{1,5})(不舒服|难受|不适)",
            r"(血压|血糖|血脂|心率|体温)(高|低|升高|下降|不稳定)",
            r"(失眠|睡不着|睡眠不好|多梦|早醒)",
            r"(食欲不振|没胃口|不想吃|吃不下)",
            r"(乏力|疲劳|没力气|精神不好|萎靡)"
        ]
    
    async def extract_keywords(
        self, 
        query: str, 
        session_id: Optional[str] = None,
        strategy: str = "hybrid"  # nlp, llm, hybrid
    ) -> List[MedicalKeyword]:
        """
        提取医疗关键词
        
        Args:
            query: 用户查询
            session_id: 会话ID（用于上下文）
            strategy: 提取策略 nlp/llm/hybrid
            
        Returns:
            医疗关键词列表
        """
        if not query or not query.strip():
            return []
        
        self.logger.info(f"🔍 开始提取医疗关键词: {query[:50]}...")
        
        if strategy == "nlp":
            return await self._extract_with_nlp(query)
        elif strategy == "llm":
            return await self._extract_with_llm(query, session_id)
        else:  # hybrid
            return await self._extract_hybrid(query, session_id)
    
    async def _extract_with_nlp(self, query: str) -> List[MedicalKeyword]:
        """使用NLP方法提取关键词"""
        keywords = []
        
        # 1. 词典匹配
        dict_keywords = self._extract_from_dictionary(query)
        keywords.extend(dict_keywords)
        
        # 2. 模式匹配
        pattern_keywords = self._extract_from_patterns(query)
        keywords.extend(pattern_keywords)
        
        # 3. 分词 + 词性标注
        seg_keywords = self._extract_from_segmentation(query)
        keywords.extend(seg_keywords)
        
        # 去重并排序
        unique_keywords = self._deduplicate_keywords(keywords)
        
        self.logger.info(f"✅ NLP提取完成: {len(unique_keywords)} 个关键词")
        return unique_keywords
    
    def _extract_from_dictionary(self, query: str) -> List[MedicalKeyword]:
        """从词典中匹配关键词"""
        keywords = []
        query_lower = query.lower()
        
        for category, words in self.medical_dict.items():
            for word in words:
                if word in query:
                    # 检查上下文，避免误匹配
                    if self._validate_context(query, word):
                        keyword = MedicalKeyword(
                            keyword=word,
                            category=category,
                            confidence=0.9,  # 词典匹配置信度高
                            source="dict",
                            context=self._extract_context(query, word)
                        )
                        keywords.append(keyword)
        
        return keywords
    
    def _extract_from_patterns(self, query: str) -> List[MedicalKeyword]:
        """从模式中提取关键词"""
        keywords = []
        
        for pattern in self.symptom_patterns:
            matches = re.finditer(pattern, query)
            for match in matches:
                matched_text = match.group()
                if len(matched_text) >= 2:  # 避免过短的匹配
                    keyword = MedicalKeyword(
                        keyword=matched_text,
                        category="症状",
                        confidence=0.7,  # 模式匹配置信度中等
                        source="pattern",
                        context=query[max(0, match.start()-10):match.end()+10]
                    )
                    keywords.append(keyword)
        
        return keywords
    
    def _extract_from_segmentation(self, query: str) -> List[MedicalKeyword]:
        """从分词结果中提取关键词"""
        keywords = []
        
        try:
            # 词性标注
            words = pseg.cut(query)
            
            for word, flag in words:
                # 医疗相关词性和长度过滤
                if (len(word) >= 2 and 
                    (flag.startswith('n') or flag.startswith('v') or flag.startswith('a')) and
                    self._is_medical_related(word)):
                    
                    category = self._classify_word(word)
                    if category:
                        keyword = MedicalKeyword(
                            keyword=word,
                            category=category,
                            confidence=0.6,  # 分词结果置信度较低
                            source="seg",
                            context=self._extract_context(query, word)
                        )
                        keywords.append(keyword)
        
        except Exception as e:
            self.logger.warning(f"⚠️ 分词提取失败: {e}")
        
        return keywords
    
    async def _extract_with_llm(self, query: str, session_id: Optional[str] = None) -> List[MedicalKeyword]:
        """使用LLM提取关键词"""
        try:
            # 构建LLM prompt
            prompt = self._build_llm_prompt(query)
            
            # 调用LLM（这里需要集成到现有的agent系统）
            llm_result = await self._call_llm_for_extraction(prompt)
            
            # 解析LLM结果
            keywords = self._parse_llm_result(llm_result, query)
            
            self.logger.info(f"✅ LLM提取完成: {len(keywords)} 个关键词")
            return keywords
            
        except Exception as e:
            self.logger.warning(f"⚠️ LLM提取失败: {e}")
            return []
    
    async def _extract_hybrid(self, query: str, session_id: Optional[str] = None) -> List[MedicalKeyword]:
        """混合策略提取关键词"""
        # 1. 快速NLP提取
        nlp_keywords = await self._extract_with_nlp(query)
        
        # 2. 如果NLP结果不够丰富，使用LLM补充
        if len(nlp_keywords) < 2 and self.use_llm_verification:
            try:
                llm_keywords = await asyncio.wait_for(
                    self._extract_with_llm(query, session_id),
                    timeout=self.llm_timeout
                )
                
                # 合并结果，LLM结果优先级更高
                all_keywords = llm_keywords + nlp_keywords
                unique_keywords = self._deduplicate_keywords(all_keywords)
                
                self.logger.info(f"✅ 混合提取完成: NLP={len(nlp_keywords)}, LLM={len(llm_keywords)}, 总计={len(unique_keywords)}")
                return unique_keywords
                
            except asyncio.TimeoutError:
                self.logger.warning("⚠️ LLM提取超时，使用NLP结果")
            except Exception as e:
                self.logger.warning(f"⚠️ LLM提取失败，使用NLP结果: {e}")
        
        return nlp_keywords
    
    def _build_llm_prompt(self, query: str) -> str:
        """构建LLM提取prompt"""
        return f"""
请从以下用户查询中提取医疗相关的关键词，包括疾病、症状、药物、治疗方法等。

用户查询："{query}"

请按以下JSON格式返回：
{{
    "keywords": [
        {{
            "keyword": "关键词",
            "category": "疾病|症状|药物|治疗|检查",
            "confidence": 0.9
        }}
    ]
}}

注意：
1. 只提取明确的医疗相关词汇
2. confidence范围0.1-1.0
3. 避免提取过于宽泛的词汇
4. 如果没有医疗关键词，返回空数组
"""
    
    async def _call_llm_for_extraction(self, prompt: str) -> str:
        """调用LLM进行关键词提取"""
        # 这里应该集成到现有的agent系统
        # 暂时返回模拟结果
        return '{"keywords": []}'
    
    def _parse_llm_result(self, llm_result: str, original_query: str) -> List[MedicalKeyword]:
        """解析LLM返回结果"""
        keywords = []
        
        try:
            import json
            data = json.loads(llm_result)
            
            for item in data.get("keywords", []):
                keyword = MedicalKeyword(
                    keyword=item["keyword"],
                    category=item["category"],
                    confidence=item["confidence"],
                    source="llm",
                    context=self._extract_context(original_query, item["keyword"])
                )
                keywords.append(keyword)
                
        except Exception as e:
            self.logger.warning(f"⚠️ LLM结果解析失败: {e}")
        
        return keywords
    
    def _validate_context(self, query: str, word: str) -> bool:
        """验证词汇的上下文是否合理"""
        # 简单的上下文验证
        word_pos = query.find(word)
        if word_pos == -1:
            return False
        
        # 检查前后文，避免否定语境
        before = query[max(0, word_pos-10):word_pos].lower()
        after = query[word_pos+len(word):word_pos+len(word)+10].lower()
        
        negative_words = ["不", "没", "无", "非", "否", "别", "避免"]
        return not any(neg in before or neg in after for neg in negative_words)
    
    def _extract_context(self, query: str, word: str) -> str:
        """提取词汇的上下文"""
        word_pos = query.find(word)
        if word_pos == -1:
            return query
        
        start = max(0, word_pos - 15)
        end = min(len(query), word_pos + len(word) + 15)
        return query[start:end]
    
    def _is_medical_related(self, word: str) -> bool:
        """判断词汇是否与医疗相关"""
        medical_chars = set("病痛疼酸胀麻痒肿红热血压糖脂心肝肾肺胃肠脑神经骨关节")
        return any(char in medical_chars for char in word) or len(word) >= 3
    
    def _classify_word(self, word: str) -> Optional[str]:
        """分类词汇"""
        for category, words in self.medical_dict.items():
            if word in words:
                return category
        
        # 基于字符特征分类
        if any(char in word for char in "痛疼酸胀麻痒"):
            return "症状"
        elif any(char in word for char in "病症炎癌瘤"):
            return "疾病"
        elif "药" in word or "素" in word:
            return "药物"
        
        return "其他"
    
    def _deduplicate_keywords(self, keywords: List[MedicalKeyword]) -> List[MedicalKeyword]:
        """去重关键词，保留置信度最高的"""
        keyword_map = {}
        
        for kw in keywords:
            key = kw.keyword.lower()
            if key not in keyword_map or kw.confidence > keyword_map[key].confidence:
                keyword_map[key] = kw
        
        # 按置信度排序
        result = list(keyword_map.values())
        result.sort(key=lambda x: x.confidence, reverse=True)
        
        return result
    
    def format_keywords_for_fhir(self, keywords: List[MedicalKeyword]) -> Dict[str, List[str]]:
        """格式化关键词用于FHIR更新"""
        fhir_data = defaultdict(list)
        
        for kw in keywords:
            if kw.confidence >= 0.7:  # 只使用高置信度的关键词
                fhir_data[kw.category].append(kw.keyword)
        
        return dict(fhir_data)


# 全局实例
_global_extractor = None

def get_medical_keyword_extractor() -> MedicalKeywordExtractor:
    """获取全局医疗关键词提取器实例"""
    global _global_extractor
    if _global_extractor is None:
        _global_extractor = MedicalKeywordExtractor()
    return _global_extractor 