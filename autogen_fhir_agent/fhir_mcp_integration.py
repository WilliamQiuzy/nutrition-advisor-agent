"""
FHIR MCP集成模块
通过MCP服务器与FHIR数据交互
"""

import requests
import json
import logging
from typing import Dict, Any, List, Optional
import os

logger = logging.getLogger(__name__)

class FHIRMCPClient:
    """FHIR MCP客户端"""
    
    def __init__(self, mcp_server_url: Optional[str] = None):
        """
        初始化FHIR MCP客户端
        
        Args:
            mcp_server_url: MCP服务器URL，默认为http://localhost:8004
        """
        self.mcp_server_url = mcp_server_url or os.getenv('FHIR_MCP_URL', 'http://localhost:8004')
        self.session = requests.Session()
        
    def health_check(self) -> Dict[str, Any]:
        """检查MCP服务器健康状态"""
        try:
            response = self.session.get(f"{self.mcp_server_url}/health")
            return response.json() if response.status_code == 200 else {"status": "unhealthy"}
        except Exception as e:
            logger.error(f"MCP health check failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用MCP工具的通用方法"""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            response = self.session.post(
                f"{self.mcp_server_url}/rpc",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                if "result" in result:
                    return {"success": True, "data": result["result"]}
                elif "error" in result:
                    return {"success": False, "error": result["error"]}
            
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
            
        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_capabilities(self) -> Dict[str, Any]:
        """获取FHIR服务器能力"""
        return self._call_mcp_tool("get_capabilities", {})
    
    def search_patients(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        搜索患者
        
        Args:
            search_params: 搜索参数，如 {"name": "张三", "city": "广州"}
        """
        return self._call_mcp_tool("search", {
            "type": "Patient",
            "searchParam": search_params
        })
    
    def get_patient(self, patient_id: str) -> Dict[str, Any]:
        """
        获取特定患者数据
        
        Args:
            patient_id: 患者ID
        """
        return self._call_mcp_tool("read", {
            "type": "Patient",
            "id": patient_id
        })
    
    def get_patient_comprehensive_data(self, patient_id: str) -> Dict[str, Any]:
        """
        获取患者综合数据（包括观察记录、药物、条件等）
        
        Args:
            patient_id: 患者ID
        """
        return self._call_mcp_tool("get_patient_comprehensive_data", {
            "patient_id": patient_id
        })
    
    def create_patient(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建新患者
        
        Args:
            patient_data: FHIR Patient资源数据
        """
        # 注意：需要确认MCP服务器是否支持create操作
        return self._call_mcp_tool("create", {
            "type": "Patient",
            "resource": patient_data
        })
    
    def update_patient(self, patient_id: str, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新患者数据
        
        Args:
            patient_id: 患者ID
            patient_data: 更新的FHIR Patient资源数据
        """
        # 注意：需要确认MCP服务器是否支持update操作
        return self._call_mcp_tool("update", {
            "type": "Patient",
            "id": patient_id,
            "resource": patient_data
        })
    
    def search_observations(self, patient_id: str, code: Optional[str] = None) -> Dict[str, Any]:
        """
        搜索患者的观察记录
        
        Args:
            patient_id: 患者ID
            code: 观察类型代码（如血压、体重等）
        """
        search_params = {"patient": patient_id}
        if code:
            search_params["code"] = code
            
        return self._call_mcp_tool("search", {
            "type": "Observation",
            "searchParam": search_params
        })
    
    def search_conditions(self, patient_id: str) -> Dict[str, Any]:
        """
        搜索患者的疾病/健康状况
        
        Args:
            patient_id: 患者ID
        """
        return self._call_mcp_tool("search", {
            "type": "Condition",
            "searchParam": {"patient": patient_id}
        })
    
    def search_medications(self, patient_id: str) -> Dict[str, Any]:
        """
        搜索患者的用药记录
        
        Args:
            patient_id: 患者ID
        """
        return self._call_mcp_tool("search", {
            "type": "MedicationRequest",
            "searchParam": {"patient": patient_id}
        })

class FHIRIntegrationService:
    """FHIR集成服务，提供高级功能"""
    
    def __init__(self):
        self.mcp_client = FHIRMCPClient()
        from fhir_data_converter import FHIRDataConverter
        self.converter = FHIRDataConverter()
    
    def sync_patient_data(self, user_profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        同步患者数据到FHIR服务器
        
        Args:
            user_profile: 系统内部的用户配置
            
        Returns:
            同步结果
        """
        try:
            # 转换为FHIR格式
            fhir_patient = self.converter.convert_to_fhir_patient(user_profile)
            
            # 检查患者是否已存在
            patient_id = user_profile.get('user_id')
            if patient_id:
                existing = self.mcp_client.get_patient(patient_id)
                if existing.get('success'):
                    # 更新现有患者
                    result = self.mcp_client.update_patient(patient_id, fhir_patient)
                    logger.info(f"更新FHIR患者数据: {patient_id}")
                else:
                    # 创建新患者
                    result = self.mcp_client.create_patient(fhir_patient)
                    logger.info(f"创建新FHIR患者: {patient_id}")
            else:
                # 创建新患者
                result = self.mcp_client.create_patient(fhir_patient)
                logger.info("创建新FHIR患者（无ID）")
            
            return result
            
        except Exception as e:
            logger.error(f"同步患者数据失败: {e}")
            return {"success": False, "error": str(e)}
    
    def get_patient_health_summary(self, patient_id: str) -> Dict[str, Any]:
        """
        获取患者健康摘要
        
        Args:
            patient_id: 患者ID
            
        Returns:
            包含患者信息、最近观察、活跃疾病等的摘要
        """
        summary = {
            "patient_id": patient_id,
            "patient_info": None,
            "recent_observations": [],
            "active_conditions": [],
            "current_medications": []
        }
        
        try:
            # 获取患者基本信息
            patient_result = self.mcp_client.get_patient(patient_id)
            if patient_result.get('success'):
                fhir_patient = patient_result['data']
                # 转换为内部格式
                summary['patient_info'] = self.converter.convert_from_fhir_patient(fhir_patient)
            
            # 获取综合数据
            comprehensive_result = self.mcp_client.get_patient_comprehensive_data(patient_id)
            if comprehensive_result.get('success'):
                data = comprehensive_result['data']
                
                # 提取最近观察
                if 'observations' in data:
                    summary['recent_observations'] = data['observations'][:5]  # 最近5条
                
                # 提取活跃疾病
                if 'conditions' in data:
                    active_conditions = [c for c in data['conditions'] 
                                       if c.get('clinicalStatus', {}).get('coding', [{}])[0].get('code') == 'active']
                    summary['active_conditions'] = active_conditions
                
                # 提取当前用药
                if 'medications' in data:
                    summary['current_medications'] = data['medications']
            
            return {"success": True, "summary": summary}
            
        except Exception as e:
            logger.error(f"获取患者健康摘要失败: {e}")
            return {"success": False, "error": str(e)}

# 使用示例
if __name__ == "__main__":
    # 初始化客户端
    client = FHIRMCPClient()
    
    # 健康检查
    print("Health Check:", client.health_check())
    
    # 获取服务器能力
    print("\nCapabilities:", client.get_capabilities())
    
    # 搜索患者
    search_result = client.search_patients({"name": "张"})
    print("\nSearch Result:", search_result)
    
    # 集成服务示例
    service = FHIRIntegrationService()
    
    # 同步用户数据
    user_profile = {
        "user_id": "test123",
        "name": "测试用户",
        "age": 30,
        "gender": "男",
        "medical_history": ["高血压"]
    }
    
    sync_result = service.sync_patient_data(user_profile)
    print("\nSync Result:", sync_result)