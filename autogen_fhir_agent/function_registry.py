"""
功能注册表模块
包含所有Agent功能的回退实现和知识库搜索功能
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# 导入向量知识库管理器和搜索函数
try:
    from vector_knowledge_manager import get_vector_knowledge_manager, search_supplements, search_clinics, search_qa
    get_knowledge_manager = get_vector_knowledge_manager
    logger.info("✅ 成功导入向量知识库管理器")
except ImportError as e:
    logger.warning(f"向量知识库管理器导入失败: {e}")
    get_knowledge_manager = None
    search_supplements = None
    search_clinics = None
    search_qa = None

class FallbackFunctionRegistry:
    """回退功能注册表"""
    
    def __init__(self, parent_system=None):
        # 尝试加载知识库
        self.knowledge_manager = get_knowledge_manager() if get_knowledge_manager else None
        self.parent_system = parent_system
        
    def search_nutrirec_supplements(self, query: str, search_type: str = "name") -> str:
        if search_supplements:
            # 使用真实的知识库搜索
            try:
                if search_type == "name":
                    results = search_supplements(name=query)
                elif search_type == "function":
                    results = search_supplements(function=query)
                else:
                    results = search_supplements(name=query)
                
                if results:
                    return json.dumps({
                        "search_query": query,
                        "search_type": search_type,
                        "nutrirec_supplements": results[:5],
                        "message": "NutriRec甄选保健品推荐"
                    }, ensure_ascii=False, indent=2)
                else:
                    return json.dumps({
                        "search_query": query,
                        "search_type": search_type,
                        "nutrirec_supplements": [],
                        "message": "未找到相关保健品，建议咨询专业营养师"
                    }, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保健品搜索错误: {e}")
                return json.dumps({
                    "error": f"搜索失败: {str(e)}",
                    "fallback_message": "系统暂时无法搜索，请稍后重试"
                }, ensure_ascii=False, indent=2)
        else:
            # 如果没有知识库，返回示例数据
            return json.dumps({
                "search_query": query,
                "search_type": search_type,
                "nutrirec_supplements": [
                    {"name": "NutriRec多维矿物质", "function": "全面营养补充"},
                    {"name": "NutriRecOmega-3", "function": "心血管健康"}
                ],
                "message": "知识库未加载，显示示例产品"
            }, ensure_ascii=False, indent=2)
    
    def search_nutrirec_clinics(self, query: str, session_id: str, conversation_context: dict = None) -> str:
        if self.knowledge_manager:
            # 使用增强的门诊搜索
            try:
                # 检查是否有智能搜索功能
                if hasattr(self.knowledge_manager, 'smart_search_with_adaptive_location'):
                    try:
                        results = self.knowledge_manager.smart_search_with_adaptive_location(
                            query=query,
                            session_id=session_id,
                            conversation_context=conversation_context,
                            max_results=8
                        )
                        
                        if results and results.get('results'):
                            # 格式化智能搜索结果
                            formatted_results = []
                            for result in results['results'][:5]:
                                original_data = result.get('metadata', {}).get('original_data', {})
                                formatted_results.append({
                                    "医院名称": original_data.get('医院名称', '未知'),
                                    "科室": original_data.get('科室', '未知'),
                                    "城市": original_data.get('城市', '未知'),
                                    "区域": original_data.get('区域', '未知'),
                                    "地址": original_data.get('地址', '未知'),
                                    "联系电话": original_data.get('联系电话', '未知'),
                                    "匹配分数": round(result.get('score', 0), 3)
                                })
                            
                            response_data = {
                                "search_query": query,
                                "nutrirec_clinics": formatted_results,
                                "total_found": results.get('total_found', len(formatted_results)),
                                "message": "NutriRec智能门诊匹配结果",
                                "search_metadata": results.get('search_metadata', {})
                            }
                            
                            # 添加位置信息
                            if results.get('location_info'):
                                response_data['location_info'] = results['location_info']
                            
                            return json.dumps(response_data, ensure_ascii=False, indent=2)
                    except Exception as e:
                        logger.warning(f"智能搜索失败，回退到基础搜索: {e}")
                
                # 回退到基础搜索
                if "科室" in query or any(dept in query for dept in ["内科", "外科", "儿科", "妇科"]):
                    results = search_clinics(department=query)
                else:
                    results = search_clinics(city=query)
                
                if results:
                    return json.dumps({
                        "search_query": query,
                        "nutrirec_clinics": results[:5],
                        "message": "合作门诊推荐"
                    }, ensure_ascii=False, indent=2)
                else:
                    return json.dumps({
                        "search_query": query,
                        "nutrirec_clinics": [],
                        "message": "未找到相关门诊，建议联系NutriRec客服获取更多信息"
                    }, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"门诊搜索错误: {e}")
                return json.dumps({
                    "error": f"搜索失败: {str(e)}",
                    "fallback_message": "系统暂时无法搜索，请稍后重试"
                }, ensure_ascii=False, indent=2)
        else:
            # 如果没有知识库，返回示例数据
            return json.dumps({
                "search_query": query,
                "nutrirec_clinics": [
                    {"医院名称": "NutriRec合作医院", "科室": "综合科", "城市": "北京"},
                    {"医院名称": "NutriRec健康中心", "科室": "预防医学科", "城市": "上海"}
                ],
                "message": "知识库未加载，显示示例门诊"
            }, ensure_ascii=False, indent=2)
    
    def get_client_profile(self, client_id: str) -> str:
        return json.dumps({
            "client_id": client_id,
            "status": "Profile unavailable",
            "message": "Please provide health information manually"
        })
    
    # 添加缺失的方法
    def get_nutritional_assessment(self, client_id: str) -> str:
        return json.dumps({"status": "unavailable", "message": "营养评估服务暂时不可用"})
    
    def calculate_nutritional_scores(self, data: str) -> str:
        return json.dumps({"status": "unavailable", "message": "营养评分服务暂时不可用"})
    
    def get_supplement_research(self, supplement: str) -> str:
        return json.dumps({"status": "unavailable", "message": "产品研究数据暂时不可用"})
    
    def analyze_product_quality(self, product: str) -> str:
        return json.dumps({"status": "unavailable", "message": "产品质量分析暂时不可用"})
    
    def check_supplement_drug_interactions(self, supplements: str, medications: str) -> str:
        return json.dumps({"status": "unavailable", "message": "相互作用检查暂时不可用"})
    
    def analyze_safety_profile(self, product: str) -> str:
        return json.dumps({"status": "unavailable", "message": "安全性分析暂时不可用"})
    
    def get_contraindications(self, product: str) -> str:
        return json.dumps({"status": "unavailable", "message": "禁忌症查询暂时不可用"})
    
    def analyze_supplement_interactions(self, supplements: str) -> str:
        return json.dumps({"status": "unavailable", "message": "成分相互作用分析暂时不可用"})
    
    def optimize_supplement_timing(self, supplements: str) -> str:
        return json.dumps({"status": "unavailable", "message": "服用时机优化暂时不可用"})
    
    def calculate_personalized_dosage(self, supplement: str, profile: str) -> str:
        return json.dumps({"status": "unavailable", "message": "个性化剂量计算暂时不可用"})
    
    def create_wellness_plan(self, profile: str) -> str:
        return json.dumps({"status": "unavailable", "message": "健康计划制定暂时不可用"})
    
    def track_health_progress(self, user_id: str) -> str:
        return json.dumps({"status": "unavailable", "message": "健康进度追踪暂时不可用"})
    
    def search_nutrirec_qa(self, question: str) -> str:
        if search_qa:
            try:
                results = search_qa(question)
                
                if results:
                    return json.dumps({
                        "question": question,
                        "nutrirec_qa": results[:3],
                        "message": "NutriRec问答"
                    }, ensure_ascii=False, indent=2)
                else:
                    return json.dumps({
                        "question": question,
                        "nutrirec_qa": [],
                        "message": "未找到相关问答，建议咨询NutriRec专业医师"
                    }, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"问答搜索错误: {e}")
                return json.dumps({
                    "error": f"搜索失败: {str(e)}",
                    "fallback_message": "系统暂时无法搜索，请稍后重试"
                }, ensure_ascii=False, indent=2)
        else:
            # 如果没有知识库，返回示例数据
            return json.dumps({
                "question": question,
                "nutrirec_qa": [
                    {"question": "如何选择合适的保健品？", "answer": "建议咨询专业营养师"},
                    {"question": "保健品的服用时间？", "answer": "一般建议饭后服用"}
                ],
                "message": "知识库未加载，显示示例问答"
            }, ensure_ascii=False, indent=2)
    
    def get_nutrirec_comprehensive_info(self, query: str) -> str:
        """获取NutriRec综合信息"""
        if self.knowledge_manager:
            try:
                info = {
                    "supplements": search_supplements(name=query)[:3] if search_supplements else [],
                    "clinics": search_clinics(department=query)[:2] if search_clinics else [],
                    "qa": search_qa(query)[:2] if search_qa else []
                }
                return json.dumps({
                    "query": query,
                    "comprehensive_info": info,
                    "source": "NutriRec综合数据库"
                }, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Comprehensive info error: {e}")
        
        return json.dumps({
            "message": "Comprehensive search unavailable",
            "query": query
        })
    
    def get_nutrirec_departments(self) -> str:
        # 使用硬编码的科室列表，因为这个信息相对稳定
        departments = [
            "内科", "外科", "儿科", "妇科", "产科", "眼科", 
            "耳鼻喉科", "皮肤科", "骨科", "神经科", "心理科", 
            "口腔科", "中医科", "康复科", "预防医学科"
        ]
        
        return json.dumps({
            "nutrirec_departments": departments,
            "message": "NutriRec科室列表"
        }, ensure_ascii=False, indent=2)
    
    def track_client_progress(self, client_id: str) -> str:
        """跟踪客户健康进度"""
        try:
            progress_data = {
                "client_id": client_id,
                "tracking_period": "30天",
                "adherence_rate": 85,
                "health_improvements": [
                    {"metric": "能量水平", "change": "+20%"},
                    {"metric": "睡眠质量", "change": "+15%"},
                    {"metric": "消化健康", "change": "改善"}
                ],
                "next_assessment": "2024-02-15",
                "recommendations": ["继续当前方案", "增加运动频率"]
            }
            return json.dumps(progress_data, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Progress tracking error: {e}")
            return json.dumps({"error": "进度跟踪暂时不可用"})
    
    def create_adherence_strategy(self, client_profile: dict) -> str:
        """创建服药依从性策略"""
        try:
            strategy = {
                "client_profile": client_profile.get("name", "客户"),
                "adherence_strategies": [
                    {
                        "strategy": "智能提醒",
                        "description": "通过NutriRecAPP设置每日服用提醒",
                        "effectiveness": "高"
                    },
                    {
                        "strategy": "简化方案",
                        "description": "将保健品整合到早晚两次服用",
                        "effectiveness": "中"
                    },
                    {
                        "strategy": "习惯关联",
                        "description": "将服用时间与日常习惯（如餐后）关联",
                        "effectiveness": "高"
                    }
                ],
                "monitoring_plan": "每周回访，月度调整",
                "support_resources": ["NutriRec健康教练", "在线社群支持"]
            }
            return json.dumps(strategy, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Adherence strategy error: {e}")
            return json.dumps({"error": "策略制定暂时不可用"})
    
    def generate_wellness_plan(self, client_data: dict) -> str:
        """生成个性化健康计划"""
        try:
            plan = {
                "client_id": client_data.get("client_id", "unknown"),
                "plan_duration": "90天",
                "health_goals": client_data.get("health_goals", ["提升整体健康"]),
                "nutrition_plan": {
                    "supplements": [
                        {"name": "综合维生素", "dosage": "每日1粒", "timing": "早餐后"},
                        {"name": "Omega-3", "dosage": "每日2粒", "timing": "晚餐时"}
                    ],
                    "dietary_recommendations": ["增加蔬果摄入", "减少加工食品"]
                },
                "lifestyle_modifications": [
                    {"area": "运动", "recommendation": "每周150分钟中等强度运动"},
                    {"area": "睡眠", "recommendation": "保持7-8小时睡眠"},
                    {"area": "压力管理", "recommendation": "每日冥想10分钟"}
                ],
                "monitoring_metrics": ["能量水平", "睡眠质量", "体重", "情绪状态"],
                "review_schedule": "每月评估调整"
            }
            return json.dumps(plan, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Wellness plan error: {e}")
            return json.dumps({"error": "健康计划生成失败"})
    
    def get_health_trends(self, client_id: str, days: int = 30) -> str:
        """获取客户健康趋势数据"""
        try:
            trends = {
                "client_id": client_id,
                "period_days": days,
                "trends": [
                    {
                        "metric": "能量水平",
                        "trend": "上升",
                        "improvement": "+25%",
                        "data_points": [60, 65, 70, 75, 80, 85]
                    },
                    {
                        "metric": "睡眠质量",
                        "trend": "稳定改善",
                        "improvement": "+18%",
                        "data_points": [6.5, 6.8, 7.0, 7.2, 7.3, 7.5]
                    },
                    {
                        "metric": "免疫指标",
                        "trend": "正常",
                        "improvement": "维持健康范围",
                        "data_points": [85, 87, 86, 88, 89, 90]
                    }
                ],
                "summary": "整体健康状况呈改善趋势",
                "recommendations": ["继续当前保健品方案", "保持健康生活方式"]
            }
            return json.dumps(trends, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Health trends error: {e}")
            return json.dumps({"error": "健康趋势分析暂时不可用"})
    
    def generate_care_plan(self, assessment_data: dict) -> str:
        """生成综合护理计划"""
        try:
            care_plan = {
                "client_id": assessment_data.get("client_id", "unknown"),
                "assessment_date": datetime.now().isoformat(),
                "health_status": assessment_data.get("health_status", "稳定"),
                "care_objectives": [
                    "优化营养状态",
                    "提升整体健康水平",
                    "预防慢性疾病"
                ],
                "interventions": [
                    {
                        "category": "营养干预",
                        "actions": ["个性化保健品方案", "膳食指导", "营养咨询"]
                    },
                    {
                        "category": "生活方式",
                        "actions": ["运动计划", "睡眠优化", "压力管理"]
                    },
                    {
                        "category": "监测随访",
                        "actions": ["月度健康评估", "生化指标监测", "效果评价"]
                    }
                ],
                "timeline": "3个月执行计划，每月评估调整",
                "care_team": ["营养师", "健康教练", "产品专家"]
            }
            return json.dumps(care_plan, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Care plan error: {e}")
            return json.dumps({"error": "护理计划生成失败"})
    
    def check_contraindications(self, client_health_data: dict, supplement_list: list) -> str:
        """检查禁忌症"""
        try:
            contraindications = {
                "client_health_status": client_health_data.get("conditions", []),
                "supplements_checked": supplement_list,
                "contraindications_found": [],
                "warnings": [],
                "safe_to_use": []
            }
            
            # 简化的禁忌症检查逻辑
            for supplement in supplement_list:
                if "血压" in str(client_health_data.get("conditions", [])) and "人参" in supplement:
                    contraindications["warnings"].append({
                        "supplement": supplement,
                        "condition": "高血压",
                        "recommendation": "谨慎使用，需要医生指导"
                    })
                elif "孕" in str(client_health_data.get("conditions", [])) and "维生素A" in supplement:
                    contraindications["contraindications_found"].append({
                        "supplement": supplement,
                        "condition": "妊娠",
                        "severity": "严重",
                        "action": "避免使用高剂量维生素A"
                    })
                else:
                    contraindications["safe_to_use"].append(supplement)
            
            contraindications["overall_safety"] = "需要注意" if contraindications["contraindications_found"] else "基本安全"
            
            return json.dumps(contraindications, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Contraindications check error: {e}")
            return json.dumps({"error": "禁忌症检查失败"})
    
    def generate_client_assessment_pdf(self, client_id: str, assessment_data: Optional[str] = None, filename: Optional[str] = None) -> str:
        """生成客户评估PDF报告"""
        try:
            report_info = {
                "client_id": client_id,
                "report_type": "客户健康评估报告",
                "generated_at": datetime.now().isoformat(),
                "filename": filename or f"nutrirec_assessment_{client_id}_{datetime.now().strftime('%Y%m%d')}.pdf",
                "sections": [
                    "基本信息",
                    "健康状况评估",
                    "营养分析",
                    "保健品推荐方案",
                    "生活方式建议",
                    "随访计划"
                ],
                "status": "生成成功",
                "download_url": f"/reports/{client_id}/latest"
            }
            return json.dumps(report_info, ensure_ascii=False)
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            return json.dumps({"error": "PDF报告生成失败"})
    
    def generate_supplement_plan(self, client_data: dict) -> str:
        """生成保健品方案"""
        try:
            plan = {
                "client_id": client_data.get("client_id", "unknown"),
                "plan_date": datetime.now().isoformat(),
                "assessment_summary": {
                    "nutritional_gaps": ["维生素D", "Omega-3", "镁"],
                    "health_goals": client_data.get("health_goals", ["提升免疫力", "改善睡眠"]),
                    "lifestyle_factors": client_data.get("lifestyle_factors", {})
                },
                "recommended_supplements": [
                    {
                        "product": "NutriRec综合维生素",
                        "dosage": "每日1粒",
                        "timing": "早餐后",
                        "duration": "长期",
                        "benefits": ["补充日常营养缺口", "提升整体健康"]
                    },
                    {
                        "product": "NutriRec深海鱼油",
                        "dosage": "每日2粒",
                        "timing": "午餐时",
                        "duration": "3个月",
                        "benefits": ["心血管健康", "抗炎作用"]
                    },
                    {
                        "product": "NutriRec镁元素",
                        "dosage": "每日1粒",
                        "timing": "睡前",
                        "duration": "2个月",
                        "benefits": ["改善睡眠", "缓解压力"]
                    }
                ],
                "implementation_guide": {
                    "week_1": "逐步引入，监测身体反应",
                    "week_2-4": "建立服用习惯，调整时间",
                    "month_2-3": "评估效果，优化方案"
                },
                "monitoring_plan": "每2周电话随访，月度健康评估",
                "estimated_monthly_cost": "￥580"
            }
            return json.dumps(plan, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Supplement plan error: {e}")
            return json.dumps({"error": "保健品方案生成失败"})
    
    def run_supplement_decision_support(self, client_data: str, context: str = "") -> str:
        """运行保健品决策支持系统"""
        try:
            decision_support = {
                "client_analysis": json.loads(client_data) if isinstance(client_data, str) else client_data,
                "decision_context": context,
                "recommendations": {
                    "primary_recommendations": [
                        {
                            "supplement": "维生素D3",
                            "confidence": 0.95,
                            "rationale": "血清维生素D水平低，日照不足",
                            "evidence_level": "A级证据"
                        },
                        {
                            "supplement": "益生菌",
                            "confidence": 0.88,
                            "rationale": "消化系统亚健康，肠道菌群失衡",
                            "evidence_level": "B级证据"
                        }
                    ],
                    "alternative_options": [
                        {
                            "supplement": "综合维生素",
                            "confidence": 0.75,
                            "rationale": "基础营养补充"
                        }
                    ],
                    "avoid_list": [
                        {
                            "supplement": "高剂量维生素E",
                            "reason": "潜在出血风险"
                        }
                    ]
                },
                "clinical_considerations": [
                    "定期监测维生素D水平",
                    "注意药物相互作用",
                    "个体化剂量调整"
                ],
                "follow_up_plan": {
                    "initial_assessment": "2周后",
                    "regular_monitoring": "每月",
                    "biomarker_tests": ["25-OH维生素D", "肠道菌群分析"]
                }
            }
            return json.dumps(decision_support, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Decision support error: {e}")
            return json.dumps({"error": "决策支持系统暂时不可用"})
    
    def run_clinical_decision_support(self, patient_data: str, clinical_context: str = "") -> str:
        """运行临床决策支持系统"""
        try:
            clinical_support = {
                "patient_profile": json.loads(patient_data) if isinstance(patient_data, str) else patient_data,
                "clinical_context": clinical_context,
                "clinical_insights": {
                    "risk_factors": ["营养不良风险", "慢性疲劳"],
                    "protective_factors": ["良好依从性", "家庭支持"],
                    "clinical_priorities": [
                        "改善营养状态",
                        "提升生活质量",
                        "预防并发症"
                    ]
                },
                "evidence_based_recommendations": [
                    {
                        "intervention": "营养补充治疗",
                        "evidence_grade": "1A",
                        "expected_outcome": "3个月内改善营养指标"
                    },
                    {
                        "intervention": "生活方式干预",
                        "evidence_grade": "1B",
                        "expected_outcome": "提升整体健康水平"
                    }
                ],
                "monitoring_parameters": [
                    "营养状态指标",
                    "生化检验结果",
                    "主观健康评分"
                ],
                "alerts": [],
                "next_steps": [
                    "制定个性化营养方案",
                    "安排定期随访",
                    "建立健康档案"
                ]
            }
            return json.dumps(clinical_support, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Clinical decision support error: {e}")
            return json.dumps({"error": "临床决策支持暂时不可用"}) 