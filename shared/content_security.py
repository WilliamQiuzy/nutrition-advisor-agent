"""
Content Security Filter for Healthcare AI Responses
Ensures safe, compliant, and appropriate content with medical disclaimers
"""

import re
import json
import logging
import hashlib
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import asyncio

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ContentType(Enum):
    """Types of content in responses"""
    MEDICAL_ADVICE = "medical_advice"
    SUPPLEMENT_RECOMMENDATION = "supplement_recommendation"
    HEALTH_INFORMATION = "health_information"
    GENERAL_WELLNESS = "general_wellness"
    EMERGENCY_GUIDANCE = "emergency_guidance"
    UNKNOWN = "unknown"


class RiskLevel(Enum):
    """Risk levels for content"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class ContentViolation:
    """Content violation details"""
    violation_type: str
    severity: RiskLevel
    description: str
    matched_text: str
    replacement_suggestion: Optional[str] = None


@dataclass
class MedicalDisclaimer:
    """Medical disclaimer configuration"""
    disclaimer_id: str
    content_type: ContentType
    disclaimer_text: str
    language: str = "zh"
    position: str = "end"  # "start", "end", "both"
    required: bool = True


class ContentSecurityFilter:
    """
    Comprehensive content security filter for healthcare AI responses
    Ensures compliance with medical regulations and ethical guidelines
    """
    
    def __init__(
        self,
        enable_medical_disclaimers: bool = True,
        enable_sensitive_content_filtering: bool = True,
        enable_brand_protection: bool = True,
        custom_disclaimers: Optional[List[MedicalDisclaimer]] = None
    ):
        self.enable_medical_disclaimers = enable_medical_disclaimers
        self.enable_sensitive_content_filtering = enable_sensitive_content_filtering
        self.enable_brand_protection = enable_brand_protection
        
        # Initialize patterns and rules
        self.harmful_patterns = self._initialize_harmful_patterns()
        self.sensitive_medical_terms = self._initialize_medical_terms()
        self.protected_brands = self._initialize_brand_protection()
        self.disclaimers = self._initialize_disclaimers(custom_disclaimers)
        
        # Statistics
        self.stats = {
            "total_filtered": 0,
            "violations_by_type": {},
            "disclaimers_added": 0
        }
    
    def _initialize_harmful_patterns(self) -> List[Tuple[re.Pattern, str, RiskLevel]]:
        """Initialize patterns for harmful content detection"""
        patterns = [
            # Absolute medical claims
            (re.compile(r"(一定|肯定|绝对|保证).*(治愈|治疗|康复|痊愈)", re.I), 
             "absolute_medical_claim", RiskLevel.HIGH),
            (re.compile(r"(definitely|certainly|guarantee).*(cure|treat|heal)", re.I),
             "absolute_medical_claim", RiskLevel.HIGH),
            
            # Dangerous medical advice
            (re.compile(r"(停止|不要|别).*(服用|吃).*(药|医嘱)", re.I),
             "dangerous_medical_advice", RiskLevel.CRITICAL),
            (re.compile(r"(stop|don't|avoid).*(taking|using).*(medication|prescription)", re.I),
             "dangerous_medical_advice", RiskLevel.CRITICAL),
            
            # Unverified claims
            (re.compile(r"(科学证明|研究表明|临床证实)(?!.*可能)", re.I),
             "unverified_claim", RiskLevel.MEDIUM),
            (re.compile(r"(scientifically proven|studies show|clinically proven)(?!.*may)", re.I),
             "unverified_claim", RiskLevel.MEDIUM),
            
            # Diagnosis attempts
            (re.compile(r"(你有|您有|你患有|您患有|诊断为)", re.I),
             "diagnosis_attempt", RiskLevel.HIGH),
            (re.compile(r"(you have|you suffer from|diagnosed with)", re.I),
             "diagnosis_attempt", RiskLevel.HIGH),
            
            # Emergency situations
            (re.compile(r"(胸痛|呼吸困难|昏迷|中风|心脏病发作)", re.I),
             "emergency_situation", RiskLevel.CRITICAL),
            (re.compile(r"(chest pain|difficulty breathing|unconscious|stroke|heart attack)", re.I),
             "emergency_situation", RiskLevel.CRITICAL),
            
            # Prescription medication
            (re.compile(r"(处方药|抗生素|激素|麻醉|镇痛药)", re.I),
             "prescription_mention", RiskLevel.MEDIUM),
            
            # Dosage modifications
            (re.compile(r"(增加|减少|调整).*(剂量|用量|毫克|mg)", re.I),
             "dosage_modification", RiskLevel.HIGH),
        ]
        
        return patterns
    
    def _initialize_medical_terms(self) -> Set[str]:
        """Initialize sensitive medical terms requiring careful handling"""
        return {
            # Chinese terms
            "癌症", "肿瘤", "艾滋病", "HIV", "精神病", "抑郁症", "自杀", "死亡",
            "手术", "化疗", "放疗", "器官移植", "遗传病", "传染病",
            
            # English terms
            "cancer", "tumor", "AIDS", "HIV", "psychiatric", "depression", "suicide",
            "death", "surgery", "chemotherapy", "radiation", "transplant", "genetic",
            "contagious", "infectious"
        }
    
    def _initialize_brand_protection(self) -> Dict[str, str]:
        """Initialize brand protection rules"""
        return {
            # Competitor brands to handle carefully
            "竞品A": "其他品牌",
            "竞品B": "某些产品",
            
            # Protected terms
            "NutriRec": "NutriRec",
            "NutriRec": "NutriRec"
        }
    
    def _initialize_disclaimers(self, custom: Optional[List[MedicalDisclaimer]]) -> Dict[ContentType, MedicalDisclaimer]:
        """Initialize medical disclaimers"""
        default_disclaimers = {
            ContentType.MEDICAL_ADVICE: MedicalDisclaimer(
                disclaimer_id="medical_advice_zh",
                content_type=ContentType.MEDICAL_ADVICE,
                disclaimer_text="\n\n【重要提示】以上信息仅供参考，不能替代专业医疗建议。如有健康问题，请及时咨询医生或前往NutriRec门诊就诊。",
                language="zh"
            ),
            ContentType.SUPPLEMENT_RECOMMENDATION: MedicalDisclaimer(
                disclaimer_id="supplement_zh",
                content_type=ContentType.SUPPLEMENT_RECOMMENDATION,
                disclaimer_text="\n\n【温馨提示】保健品不能代替药物治疗。请根据个人体质选择，如有疑问请咨询专业医护人员。更多优质保健品请访问合作商城小程序。",
                language="zh"
            ),
            ContentType.HEALTH_INFORMATION: MedicalDisclaimer(
                disclaimer_id="health_info_zh",
                content_type=ContentType.HEALTH_INFORMATION,
                disclaimer_text="\n\n【健康提醒】健康管理需要持续关注，建议定期体检。NutriRec为您提供专业的健康管理服务。",
                language="zh"
            ),
            ContentType.EMERGENCY_GUIDANCE: MedicalDisclaimer(
                disclaimer_id="emergency_zh",
                content_type=ContentType.EMERGENCY_GUIDANCE,
                disclaimer_text="\n\n【紧急提醒】如遇紧急医疗情况，请立即拨打120急救电话或前往最近的医院急诊科！",
                language="zh",
                position="start"
            )
        }
        
        # Add custom disclaimers
        if custom:
            for disclaimer in custom:
                default_disclaimers[disclaimer.content_type] = disclaimer
        
        return default_disclaimers
    
    async def filter_content(
        self,
        content: str,
        content_type: Optional[ContentType] = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, List[ContentViolation], Dict[str, Any]]:
        """
        Filter and sanitize content
        
        Returns:
            Tuple of (filtered_content, violations, metadata)
        """
        violations = []
        filtered_content = content
        metadata = {
            "original_length": len(content),
            "filtered": False,
            "disclaimers_added": [],
            "content_type": content_type.value if content_type else "unknown"
        }
        
        # Detect content type if not provided
        if not content_type:
            content_type = self._detect_content_type(content)
            metadata["detected_content_type"] = content_type.value
        
        # Check for harmful patterns
        if self.enable_sensitive_content_filtering:
            filtered_content, pattern_violations = await self._check_harmful_patterns(filtered_content)
            violations.extend(pattern_violations)
        
        # Check for sensitive medical terms
        term_violations = await self._check_sensitive_terms(filtered_content)
        if term_violations:
            violations.extend(term_violations)
            # Add general medical disclaimer for sensitive terms
            if content_type != ContentType.EMERGENCY_GUIDANCE:
                content_type = ContentType.MEDICAL_ADVICE
        
        # Apply brand protection
        if self.enable_brand_protection:
            filtered_content = await self._apply_brand_protection(filtered_content)
        
        # Add appropriate disclaimers
        if self.enable_medical_disclaimers:
            filtered_content, added_disclaimers = await self._add_disclaimers(
                filtered_content, content_type, violations
            )
            metadata["disclaimers_added"] = added_disclaimers
        
        # Handle emergency situations specially
        if any(v.violation_type == "emergency_situation" for v in violations):
            filtered_content = await self._handle_emergency_content(filtered_content)
        
        # Update statistics
        if violations:
            self.stats["total_filtered"] += 1
            for violation in violations:
                self.stats["violations_by_type"][violation.violation_type] = \
                    self.stats["violations_by_type"].get(violation.violation_type, 0) + 1
        
        metadata["filtered"] = len(violations) > 0
        metadata["violation_count"] = len(violations)
        metadata["final_length"] = len(filtered_content)
        
        return filtered_content, violations, metadata
    
    def _detect_content_type(self, content: str) -> ContentType:
        """Detect the type of content"""
        content_lower = content.lower()
        
        # Check for emergency indicators
        emergency_keywords = ["紧急", "急救", "120", "emergency", "urgent", "立即就医"]
        if any(keyword in content_lower for keyword in emergency_keywords):
            return ContentType.EMERGENCY_GUIDANCE
        
        # Check for medical advice
        medical_keywords = ["诊断", "治疗", "症状", "疾病", "diagnosis", "treatment", "symptom"]
        if any(keyword in content_lower for keyword in medical_keywords):
            return ContentType.MEDICAL_ADVICE
        
        # Check for supplement recommendations
        supplement_keywords = ["保健品", "维生素", "营养素", "补充剂", "supplement", "vitamin"]
        if any(keyword in content_lower for keyword in supplement_keywords):
            return ContentType.SUPPLEMENT_RECOMMENDATION
        
        # Check for general health information
        health_keywords = ["健康", "养生", "饮食", "运动", "health", "wellness", "diet", "exercise"]
        if any(keyword in content_lower for keyword in health_keywords):
            return ContentType.HEALTH_INFORMATION
        
        return ContentType.GENERAL_WELLNESS
    
    async def _check_harmful_patterns(self, content: str) -> Tuple[str, List[ContentViolation]]:
        """Check for harmful patterns and filter them"""
        violations = []
        filtered_content = content
        
        for pattern, violation_type, risk_level in self.harmful_patterns:
            matches = pattern.findall(content)
            if matches:
                for match in matches:
                    violation = ContentViolation(
                        violation_type=violation_type,
                        severity=risk_level,
                        description=f"Detected {violation_type}",
                        matched_text=match if isinstance(match, str) else str(match)
                    )
                    violations.append(violation)
                    
                    # Apply filtering based on risk level
                    if risk_level == RiskLevel.CRITICAL:
                        # Remove or replace critical content
                        if violation_type == "dangerous_medical_advice":
                            filtered_content = pattern.sub(
                                "请在医生指导下调整用药", filtered_content
                            )
                        elif violation_type == "emergency_situation":
                            # Don't filter emergency terms, but flag for special handling
                            pass
                    elif risk_level == RiskLevel.HIGH:
                        # Soften high-risk content
                        if violation_type == "absolute_medical_claim":
                            filtered_content = pattern.sub(
                                lambda m: m.group(0).replace("一定", "可能").replace("肯定", "可能")
                                         .replace("definitely", "may").replace("certainly", "possibly"),
                                filtered_content
                            )
                        elif violation_type == "diagnosis_attempt":
                            filtered_content = pattern.sub(
                                "可能存在相关症状，建议咨询医生确诊", filtered_content
                            )
        
        return filtered_content, violations
    
    async def _check_sensitive_terms(self, content: str) -> List[ContentViolation]:
        """Check for sensitive medical terms"""
        violations = []
        content_lower = content.lower()
        
        for term in self.sensitive_medical_terms:
            if term.lower() in content_lower:
                violations.append(ContentViolation(
                    violation_type="sensitive_medical_term",
                    severity=RiskLevel.MEDIUM,
                    description=f"Contains sensitive medical term",
                    matched_text=term
                ))
        
        return violations
    
    async def _apply_brand_protection(self, content: str) -> str:
        """Apply brand protection rules"""
        filtered_content = content
        
        for brand, replacement in self.protected_brands.items():
            if brand in content and brand != replacement:
                filtered_content = filtered_content.replace(brand, replacement)
        
        return filtered_content
    
    async def _add_disclaimers(
        self, 
        content: str, 
        content_type: ContentType,
        violations: List[ContentViolation]
    ) -> Tuple[str, List[str]]:
        """Add appropriate disclaimers to content"""
        added_disclaimers = []
        
        # Determine which disclaimers to add
        disclaimers_to_add = []
        
        # Primary disclaimer based on content type
        if content_type in self.disclaimers:
            disclaimers_to_add.append(self.disclaimers[content_type])
        
        # Additional disclaimers based on violations
        if any(v.severity == RiskLevel.CRITICAL for v in violations):
            if ContentType.EMERGENCY_GUIDANCE in self.disclaimers:
                disclaimers_to_add.append(self.disclaimers[ContentType.EMERGENCY_GUIDANCE])
        
        # Apply disclaimers
        result_content = content
        for disclaimer in disclaimers_to_add:
            if disclaimer.position == "start":
                result_content = disclaimer.disclaimer_text + "\n\n" + result_content
            elif disclaimer.position == "both":
                result_content = disclaimer.disclaimer_text + "\n\n" + result_content + disclaimer.disclaimer_text
            else:  # default to end
                result_content = result_content + disclaimer.disclaimer_text
            
            added_disclaimers.append(disclaimer.disclaimer_id)
            self.stats["disclaimers_added"] += 1
        
        return result_content, added_disclaimers
    
    async def _handle_emergency_content(self, content: str) -> str:
        """Special handling for emergency content"""
        emergency_prefix = "紧急医疗情况 ⚠️\n\n"
        emergency_suffix = "\n\n如情况紧急，请立即拨打120或前往最近的急诊室！"
        
        if not content.startswith(emergency_prefix):
            content = emergency_prefix + content
        if not content.endswith(emergency_suffix):
            content = content + emergency_suffix
        
        return content
    
    async def validate_agent_response(
        self,
        agent_type: str,
        response: str,
        expected_format: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, List[str]]:
        """Validate that agent response meets security and format requirements"""
        issues = []
        
        # Check response length
        if len(response) > 10000:
            issues.append("Response too long (>10000 characters)")
        
        if len(response) < 10:
            issues.append("Response too short (<10 characters)")
        
        # Check for required sections based on agent type
        if agent_type == "NutritionConsultant":
            required_sections = ["营养评估", "建议"]
            for section in required_sections:
                if section not in response:
                    issues.append(f"Missing required section: {section}")
        
        elif agent_type == "SafetyAssessor":
            if "安全" not in response and "safety" not in response.lower():
                issues.append("Safety assessment missing safety evaluation")
        
        # Check for formatting issues
        if response.count('\n') > 100:
            issues.append("Excessive line breaks")
        
        # Check for potential data leakage
        sensitive_patterns = [
            r'\b\d{11}\b',  # Phone numbers
            r'\b\d{18}\b',  # ID numbers
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # Emails
        ]
        
        for pattern in sensitive_patterns:
            if re.search(pattern, response):
                issues.append(f"Potential PII detected: {pattern}")
        
        # Check expected format if provided
        if expected_format:
            try:
                # Simple format validation
                if "json" in expected_format.get("type", ""):
                    json.loads(response)
            except json.JSONDecodeError:
                issues.append("Invalid JSON format when JSON expected")
        
        is_valid = len(issues) == 0
        return is_valid, issues
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get content filtering statistics"""
        return {
            "total_content_filtered": self.stats["total_filtered"],
            "violations_by_type": dict(self.stats["violations_by_type"]),
            "disclaimers_added": self.stats["disclaimers_added"],
            "filtering_enabled": {
                "medical_disclaimers": self.enable_medical_disclaimers,
                "sensitive_content": self.enable_sensitive_content_filtering,
                "brand_protection": self.enable_brand_protection
            }
        }
    
    def add_custom_pattern(
        self,
        pattern: str,
        violation_type: str,
        risk_level: RiskLevel,
        description: str
    ):
        """Add custom filtering pattern"""
        compiled_pattern = re.compile(pattern, re.I)
        self.harmful_patterns.append((compiled_pattern, violation_type, risk_level))
        logger.info(f"Added custom pattern: {violation_type} with risk level {risk_level.name}")
    
    def update_disclaimer(self, disclaimer: MedicalDisclaimer):
        """Update or add a disclaimer"""
        self.disclaimers[disclaimer.content_type] = disclaimer
        logger.info(f"Updated disclaimer for {disclaimer.content_type.value}")


# Helper class for response formatting
class ResponseFormatter:
    """Format responses consistently with security considerations"""
    
    @staticmethod
    def format_supplement_recommendation(
        recommendations: List[Dict[str, Any]],
        user_profile: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format supplement recommendations with proper structure"""
        formatted = " NutriRec保健品推荐方案 \n\n"
        
        if user_profile:
            formatted += f"基于您的健康档案分析：\n"
            formatted += f"• 年龄：{user_profile.get('age', '未知')}\n"
            formatted += f"• 健康目标：{', '.join(user_profile.get('health_goals', ['综合健康']))}\n\n"
        
        formatted += "推荐方案：\n\n"
        
        for i, rec in enumerate(recommendations, 1):
            formatted += f"{i}. **{rec.get('name', '保健品')}**\n"
            formatted += f"   • 主要成分：{rec.get('ingredients', '详见产品说明')}\n"
            formatted += f"   • 推荐理由：{rec.get('reason', '适合您的健康需求')}\n"
            formatted += f"   • 建议用法：{rec.get('usage', '按产品说明服用')}\n"
            formatted += f"   • 注意事项：{rec.get('cautions', '请遵医嘱')}\n\n"
        
        formatted += "温馨提示：\n"
        formatted += "• 保健品不能替代均衡饮食和健康生活方式\n"
        formatted += "• 服用前请仔细阅读产品说明\n"
        formatted += "• 如有不适，请立即停用并咨询医生\n"
        
        return formatted
    
    @staticmethod
    def format_error_response(error_type: str, user_friendly: bool = True) -> str:
        """Format error responses safely"""
        if user_friendly:
            error_messages = {
                "rate_limit": "您的请求过于频繁，请稍后再试。",
                "invalid_input": "您的输入似乎有些问题，请重新描述您的需求。",
                "system_error": "系统繁忙，请稍后再试。如需帮助，请联系客服。",
                "security_violation": "您的请求包含不适当内容，请修改后重试。"
            }
            return error_messages.get(error_type, "抱歉，系统暂时无法处理您的请求。")
        else:
            # Technical error for logging
            return f"Error: {error_type}"