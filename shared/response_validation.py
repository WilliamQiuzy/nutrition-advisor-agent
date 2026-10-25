"""
Response Validation System for Multi-Agent Consistency
Ensures consistency, accuracy, and quality across multiple agent responses
"""

import re
import json
import logging
import hashlib
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import difflib
from collections import Counter
import numpy as np

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ValidationRule(Enum):
    """Types of validation rules"""
    CONSISTENCY = "consistency"
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CONFLICT_DETECTION = "conflict_detection"
    FORMAT_COMPLIANCE = "format_compliance"
    SAFETY_CHECK = "safety_check"


class ConflictType(Enum):
    """Types of conflicts between agent responses"""
    CONTRADICTION = "contradiction"
    DOSAGE_MISMATCH = "dosage_mismatch"
    TIMING_CONFLICT = "timing_conflict"
    INTERACTION_DISAGREEMENT = "interaction_disagreement"
    RECOMMENDATION_CONFLICT = "recommendation_conflict"


@dataclass
class ValidationResult:
    """Result of response validation"""
    is_valid: bool
    confidence_score: float  # 0.0 to 1.0
    issues: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    consensus_response: Optional[str] = None


@dataclass
class AgentResponse:
    """Structure for agent responses"""
    agent_type: str
    response_id: str
    content: str
    timestamp: datetime
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def extract_key_points(self) -> List[str]:
        """Extract key points from response"""
        # Simple extraction based on bullet points and numbered lists
        points = []
        
        # Extract bullet points
        bullet_pattern = r'[•·▪▫◦‣⁃]\s*(.+)'
        points.extend(re.findall(bullet_pattern, self.content))
        
        # Extract numbered points
        numbered_pattern = r'\d+\.\s*(.+)'
        points.extend(re.findall(numbered_pattern, self.content))
        
        # Extract recommendations (common patterns)
        rec_patterns = [
            r'建议[:：]\s*(.+)',
            r'推荐[:：]\s*(.+)',
            r'[Rr]ecommend(?:ation)?[:：]\s*(.+)'
        ]
        for pattern in rec_patterns:
            points.extend(re.findall(pattern, self.content))
        
        return [p.strip() for p in points if p.strip()]


class ResponseValidator:
    """
    Validates and ensures consistency across multiple agent responses
    """
    
    def __init__(
        self,
        enable_conflict_resolution: bool = True,
        min_agreement_threshold: float = 0.7,
        enable_fact_checking: bool = True
    ):
        self.enable_conflict_resolution = enable_conflict_resolution
        self.min_agreement_threshold = min_agreement_threshold
        self.enable_fact_checking = enable_fact_checking
        
        # Knowledge base for fact checking
        self.fact_patterns = self._initialize_fact_patterns()
        
        # Validation statistics
        self.stats = {
            "total_validations": 0,
            "conflicts_detected": 0,
            "resolutions_successful": 0,
            "validation_failures": 0
        }
    
    def _initialize_fact_patterns(self) -> Dict[str, Any]:
        """Initialize patterns for fact checking"""
        return {
            "dosage_ranges": {
                "维生素D": {"min": 400, "max": 4000, "unit": "IU"},
                "维生素C": {"min": 65, "max": 2000, "unit": "mg"},
                "Omega-3": {"min": 250, "max": 3000, "unit": "mg"},
                "钙": {"min": 1000, "max": 2500, "unit": "mg"},
                "铁": {"min": 8, "max": 45, "unit": "mg"},
                "维生素B12": {"min": 2.4, "max": 1000, "unit": "mcg"}
            },
            "interaction_pairs": [
                ("钙", "铁"),  # Calcium can inhibit iron absorption
                ("维生素K", "华法林"),  # Vitamin K interacts with warfarin
                ("圣约翰草", "抗抑郁药"),  # St. John's Wort interactions
            ],
            "timing_rules": {
                "铁": "空腹服用效果最佳",
                "钙": "餐后服用，避免与铁同时服用",
                "维生素D": "与含脂肪的餐食一起服用",
                "益生菌": "餐前30分钟服用"
            }
        }
    
    async def validate_responses(
        self,
        responses: List[AgentResponse],
        validation_rules: Optional[List[ValidationRule]] = None
    ) -> ValidationResult:
        """
        Validate multiple agent responses for consistency and accuracy
        """
        self.stats["total_validations"] += 1
        
        if not responses:
            return ValidationResult(is_valid=False, confidence_score=0.0, 
                                  issues=[{"type": "no_responses", "description": "No responses to validate"}])
        
        # Default validation rules
        if validation_rules is None:
            validation_rules = [
                ValidationRule.CONSISTENCY,
                ValidationRule.COMPLETENESS,
                ValidationRule.CONFLICT_DETECTION,
                ValidationRule.SAFETY_CHECK
            ]
        
        validation_results = []
        all_issues = []
        all_conflicts = []
        
        # Run each validation rule
        for rule in validation_rules:
            if rule == ValidationRule.CONSISTENCY:
                result = await self._check_consistency(responses)
                validation_results.append(result)
            elif rule == ValidationRule.COMPLETENESS:
                result = await self._check_completeness(responses)
                validation_results.append(result)
            elif rule == ValidationRule.CONFLICT_DETECTION:
                conflicts = await self._detect_conflicts(responses)
                all_conflicts.extend(conflicts)
            elif rule == ValidationRule.SAFETY_CHECK:
                result = await self._check_safety(responses)
                validation_results.append(result)
        
        # Calculate overall confidence score
        confidence_scores = [r["confidence"] for r in validation_results if "confidence" in r]
        overall_confidence = np.mean(confidence_scores) if confidence_scores else 0.5
        
        # Collect all issues
        for result in validation_results:
            if "issues" in result:
                all_issues.extend(result["issues"])
        
        # Determine if valid
        is_valid = len(all_issues) == 0 and len(all_conflicts) == 0
        
        # Generate consensus response if needed
        consensus_response = None
        if self.enable_conflict_resolution and (all_conflicts or not is_valid):
            consensus_response = await self._generate_consensus(responses, all_conflicts)
        
        # Generate suggestions
        suggestions = self._generate_suggestions(all_issues, all_conflicts)
        
        return ValidationResult(
            is_valid=is_valid,
            confidence_score=overall_confidence,
            issues=all_issues,
            conflicts=all_conflicts,
            suggestions=suggestions,
            consensus_response=consensus_response
        )
    
    async def _check_consistency(self, responses: List[AgentResponse]) -> Dict[str, Any]:
        """Check consistency across responses"""
        result = {"confidence": 1.0, "issues": []}
        
        # Extract key points from each response
        all_points = {}
        for response in responses:
            points = response.extract_key_points()
            all_points[response.agent_type] = points
        
        # Compare similarity between agent responses
        agent_types = list(all_points.keys())
        similarity_scores = []
        
        for i in range(len(agent_types)):
            for j in range(i + 1, len(agent_types)):
                agent1, agent2 = agent_types[i], agent_types[j]
                points1, points2 = all_points[agent1], all_points[agent2]
                
                # Calculate similarity
                if points1 and points2:
                    similarity = self._calculate_similarity(points1, points2)
                    similarity_scores.append(similarity)
                    
                    if similarity < self.min_agreement_threshold:
                        result["issues"].append({
                            "type": "low_consistency",
                            "agents": [agent1, agent2],
                            "similarity": similarity,
                            "description": f"Low agreement between {agent1} and {agent2}"
                        })
        
        # Update confidence based on consistency
        if similarity_scores:
            avg_similarity = np.mean(similarity_scores)
            result["confidence"] = avg_similarity
        
        return result
    
    async def _check_completeness(self, responses: List[AgentResponse]) -> Dict[str, Any]:
        """Check if responses are complete"""
        result = {"confidence": 1.0, "issues": []}
        
        required_sections = {
            "NutritionConsultant": ["营养评估", "建议", "注意事项"],
            "SupplementSpecialist": ["产品推荐", "成分说明", "使用方法"],
            "SafetyAssessor": ["安全评估", "相互作用", "禁忌"],
            "FormulationExpert": ["配方分析", "剂量", "服用时间"],
            "HealthCoach": ["生活方式", "目标", "计划"]
        }
        
        for response in responses:
            if response.agent_type in required_sections:
                missing_sections = []
                for section in required_sections[response.agent_type]:
                    if section not in response.content:
                        missing_sections.append(section)
                
                if missing_sections:
                    result["issues"].append({
                        "type": "incomplete_response",
                        "agent": response.agent_type,
                        "missing_sections": missing_sections,
                        "description": f"{response.agent_type} missing required sections"
                    })
                    result["confidence"] *= 0.8
        
        return result
    
    async def _detect_conflicts(self, responses: List[AgentResponse]) -> List[Dict[str, Any]]:
        """Detect conflicts between responses"""
        conflicts = []
        
        # Extract recommendations from each agent
        recommendations = {}
        for response in responses:
            recs = self._extract_recommendations(response.content)
            recommendations[response.agent_type] = recs
        
        # Check for dosage conflicts
        dosage_conflicts = self._check_dosage_conflicts(recommendations)
        conflicts.extend(dosage_conflicts)
        
        # Check for timing conflicts
        timing_conflicts = self._check_timing_conflicts(recommendations)
        conflicts.extend(timing_conflicts)
        
        # Check for interaction conflicts
        interaction_conflicts = self._check_interaction_conflicts(recommendations)
        conflicts.extend(interaction_conflicts)
        
        if conflicts:
            self.stats["conflicts_detected"] += len(conflicts)
        
        return conflicts
    
    def _extract_recommendations(self, content: str) -> Dict[str, Any]:
        """Extract structured recommendations from content"""
        recommendations = {
            "supplements": [],
            "dosages": {},
            "timing": {},
            "interactions": []
        }
        
        # Extract supplement names
        supplement_pattern = r'(?:推荐|建议|服用)[：:]\s*([^，。,.\n]+)'
        supplements = re.findall(supplement_pattern, content)
        recommendations["supplements"] = supplements
        
        # Extract dosages
        dosage_pattern = r'(\w+)[：:]\s*(\d+)\s*(mg|g|IU|mcg|毫克|克|国际单位)'
        dosages = re.findall(dosage_pattern, content)
        for supp, amount, unit in dosages:
            recommendations["dosages"][supp] = {"amount": float(amount), "unit": unit}
        
        # Extract timing
        timing_pattern = r'(\w+).*?(早上|晚上|餐前|餐后|空腹|睡前)'
        timings = re.findall(timing_pattern, content)
        for supp, time in timings:
            recommendations["timing"][supp] = time
        
        return recommendations
    
    def _check_dosage_conflicts(self, recommendations: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """Check for dosage conflicts between agents"""
        conflicts = []
        supplements = set()
        
        # Collect all mentioned supplements
        for agent, recs in recommendations.items():
            supplements.update(recs.get("dosages", {}).keys())
        
        # Check each supplement for dosage conflicts
        for supplement in supplements:
            dosages_by_agent = {}
            
            for agent, recs in recommendations.items():
                if supplement in recs.get("dosages", {}):
                    dosages_by_agent[agent] = recs["dosages"][supplement]
            
            if len(dosages_by_agent) > 1:
                # Check if dosages differ significantly
                amounts = [d["amount"] for d in dosages_by_agent.values()]
                if max(amounts) / min(amounts) > 1.5:  # More than 50% difference
                    conflicts.append({
                        "type": ConflictType.DOSAGE_MISMATCH.value,
                        "supplement": supplement,
                        "agents_involved": list(dosages_by_agent.keys()),
                        "dosages": dosages_by_agent,
                        "severity": "high"
                    })
        
        return conflicts
    
    def _check_timing_conflicts(self, recommendations: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """Check for timing conflicts"""
        conflicts = []
        
        # Check calcium and iron timing
        for agent, recs in recommendations.items():
            timing = recs.get("timing", {})
            if "钙" in timing and "铁" in timing:
                if timing["钙"] == timing["铁"]:
                    conflicts.append({
                        "type": ConflictType.TIMING_CONFLICT.value,
                        "agent": agent,
                        "supplements": ["钙", "铁"],
                        "issue": "Should not be taken at the same time",
                        "severity": "medium"
                    })
        
        return conflicts
    
    def _check_interaction_conflicts(self, recommendations: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """Check for interaction conflicts"""
        conflicts = []
        
        # Collect all supplements across agents
        all_supplements = set()
        for agent, recs in recommendations.items():
            all_supplements.update(recs.get("supplements", []))
        
        # Check known interactions
        for supp1, supp2 in self.fact_patterns["interaction_pairs"]:
            if supp1 in all_supplements and supp2 in all_supplements:
                conflicts.append({
                    "type": ConflictType.INTERACTION_DISAGREEMENT.value,
                    "supplements": [supp1, supp2],
                    "issue": f"Known interaction between {supp1} and {supp2}",
                    "severity": "high"
                })
        
        return conflicts
    
    async def _check_safety(self, responses: List[AgentResponse]) -> Dict[str, Any]:
        """Check safety aspects of responses"""
        result = {"confidence": 1.0, "issues": []}
        
        for response in responses:
            # Check for excessive dosages
            dosage_issues = self._check_dosage_safety(response.content)
            result["issues"].extend(dosage_issues)
            
            # Check for dangerous combinations
            if "不要" in response.content or "停止" in response.content or "stop" in response.content.lower():
                result["issues"].append({
                    "type": "safety_concern",
                    "agent": response.agent_type,
                    "description": "Contains potentially dangerous advice about stopping medication"
                })
                result["confidence"] *= 0.5
        
        return result
    
    def _check_dosage_safety(self, content: str) -> List[Dict[str, Any]]:
        """Check if recommended dosages are safe"""
        issues = []
        
        # Extract dosages from content
        dosage_pattern = r'(\w+)[：:]\s*(\d+)\s*(mg|g|IU|mcg|毫克|克|国际单位)'
        dosages = re.findall(dosage_pattern, content)
        
        for supplement, amount, unit in dosages:
            amount = float(amount)
            
            # Convert to standard units if needed
            if unit in ["毫克", "mg"]:
                unit = "mg"
            elif unit in ["克", "g"]:
                amount *= 1000
                unit = "mg"
            elif unit in ["国际单位", "IU"]:
                unit = "IU"
            
            # Check against known safe ranges
            if supplement in self.fact_patterns["dosage_ranges"]:
                safe_range = self.fact_patterns["dosage_ranges"][supplement]
                if safe_range["unit"] == unit:
                    if amount > safe_range["max"]:
                        issues.append({
                            "type": "excessive_dosage",
                            "supplement": supplement,
                            "recommended": amount,
                            "max_safe": safe_range["max"],
                            "unit": unit,
                            "severity": "high"
                        })
                    elif amount < safe_range["min"]:
                        issues.append({
                            "type": "insufficient_dosage",
                            "supplement": supplement,
                            "recommended": amount,
                            "min_effective": safe_range["min"],
                            "unit": unit,
                            "severity": "low"
                        })
        
        return issues
    
    def _calculate_similarity(self, points1: List[str], points2: List[str]) -> float:
        """Calculate similarity between two sets of points"""
        if not points1 or not points2:
            return 0.0
        
        # Use Jaccard similarity for simple comparison
        set1 = set(' '.join(points1).lower().split())
        set2 = set(' '.join(points2).lower().split())
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    async def _generate_consensus(
        self,
        responses: List[AgentResponse],
        conflicts: List[Dict[str, Any]]
    ) -> str:
        """Generate consensus response resolving conflicts"""
        consensus_parts = []
        
        # Header
        consensus_parts.append("综合评估结果（多专家共识）\n")
        
        # Collect agreements
        agreements = self._find_agreements(responses)
        if agreements:
            consensus_parts.append("专家一致认同：")
            for agreement in agreements[:5]:  # Top 5 agreements
                consensus_parts.append(f"• {agreement}")
            consensus_parts.append("")
        
        # Address conflicts
        if conflicts:
            consensus_parts.append("需要注意的事项：")
            for conflict in conflicts[:3]:  # Top 3 conflicts
                resolution = self._resolve_conflict(conflict)
                consensus_parts.append(f"• {resolution}")
            consensus_parts.append("")
        
        # Safety reminders
        consensus_parts.append("安全提醒：")
        consensus_parts.append("• 以上建议仅供参考，具体用量请遵医嘱")
        consensus_parts.append("• 如有不适，请立即停用并咨询医生")
        consensus_parts.append("• 保健品不能替代药物治疗")
        
        self.stats["resolutions_successful"] += 1
        
        return "\n".join(consensus_parts)
    
    def _find_agreements(self, responses: List[AgentResponse]) -> List[str]:
        """Find points of agreement between agents"""
        all_points = []
        for response in responses:
            all_points.extend(response.extract_key_points())
        
        # Count frequency of similar points
        point_counts = Counter()
        for i, point1 in enumerate(all_points):
            for j, point2 in enumerate(all_points[i+1:], i+1):
                if difflib.SequenceMatcher(None, point1, point2).ratio() > 0.8:
                    point_counts[point1] += 1
        
        # Return most agreed upon points
        return [point for point, count in point_counts.most_common(5) if count >= 2]
    
    def _resolve_conflict(self, conflict: Dict[str, Any]) -> str:
        """Generate resolution for a conflict"""
        conflict_type = conflict.get("type")
        
        if conflict_type == ConflictType.DOSAGE_MISMATCH.value:
            supplement = conflict.get("supplement", "补充剂")
            dosages = conflict.get("dosages", {})
            amounts = [d["amount"] for d in dosages.values()]
            avg_amount = np.mean(amounts)
            return f"{supplement}的建议剂量范围为{min(amounts)}-{max(amounts)}{list(dosages.values())[0]['unit']}，请根据个人情况选择"
        
        elif conflict_type == ConflictType.TIMING_CONFLICT.value:
            supplements = conflict.get("supplements", [])
            return f"{supplements[0]}和{supplements[1]}建议分开服用，间隔至少2小时"
        
        elif conflict_type == ConflictType.INTERACTION_DISAGREEMENT.value:
            supplements = conflict.get("supplements", [])
            return f"{supplements[0]}和{supplements[1]}可能存在相互作用，请咨询医生后使用"
        
        return "请咨询专业医疗人员获取个性化建议"
    
    def _generate_suggestions(
        self,
        issues: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate suggestions for improving responses"""
        suggestions = []
        
        # Suggestions based on issues
        issue_types = set(issue["type"] for issue in issues)
        if "incomplete_response" in issue_types:
            suggestions.append("确保所有专家提供完整的评估报告，包含所有必要部分")
        
        if "low_consistency" in issue_types:
            suggestions.append("加强专家间的协调，确保建议的一致性")
        
        # Suggestions based on conflicts
        if any(c["type"] == ConflictType.DOSAGE_MISMATCH.value for c in conflicts):
            suggestions.append("统一剂量推荐标准，参考最新临床指南")
        
        if any(c["severity"] == "high" for c in conflicts):
            suggestions.append("对高风险冲突进行专门的安全性评估")
        
        return suggestions
    
    def get_validation_stats(self) -> Dict[str, Any]:
        """Get validation statistics"""
        success_rate = (
            self.stats["resolutions_successful"] / self.stats["conflicts_detected"]
            if self.stats["conflicts_detected"] > 0 else 1.0
        )
        
        return {
            "total_validations": self.stats["total_validations"],
            "conflicts_detected": self.stats["conflicts_detected"],
            "resolution_success_rate": success_rate,
            "validation_failures": self.stats["validation_failures"]
        }


# Helper function for quick validation
async def validate_multi_agent_responses(
    responses: Dict[str, str],
    validator: Optional[ResponseValidator] = None
) -> ValidationResult:
    """
    Quick validation of multi-agent responses
    
    Args:
        responses: Dict mapping agent_type to response content
        validator: Optional validator instance
    
    Returns:
        ValidationResult
    """
    if validator is None:
        validator = ResponseValidator()
    
    # Convert to AgentResponse objects
    agent_responses = []
    for agent_type, content in responses.items():
        agent_responses.append(AgentResponse(
            agent_type=agent_type,
            response_id=f"{agent_type}_{datetime.now().timestamp()}",
            content=content,
            timestamp=datetime.now()
        ))
    
    return await validator.validate_responses(agent_responses)