"""
FHIR数据转换器
将系统内部的患者数据格式转换为FHIR R4标准格式
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)

class FHIRDataConverter:
    """FHIR R4 数据格式转换器"""
    
    def __init__(self):
        self.fhir_base_url = "http://localhost:8004"
        
    def convert_to_fhir_patient(self, user_profile: Dict[str, Any], session_data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        将系统内部的用户配置转换为FHIR R4 Patient资源格式
        
        Args:
            user_profile: 用户配置数据（来自create_conversation_session）
            session_data: 会话数据（包含地理位置等信息）
            
        Returns:
            FHIR R4 Patient资源
        """
        # 生成唯一ID
        patient_id = user_profile.get('user_id', str(uuid.uuid4()))
        
        # 构建FHIR Patient资源
        fhir_patient = {
            "resourceType": "Patient",
            "id": patient_id,
            "identifier": [
                {
                    "system": "http://nutrirec.example.com/patient-id",
                    "value": patient_id,
                    "use": "official"
                }
            ],
            "active": True,
            "name": [],
            "telecom": [],
            "gender": "unknown",  # 默认值
            "address": []
        }
        
        # 处理姓名
        if user_profile.get('name'):
            name_parts = user_profile['name'].split(' ')
            fhir_patient['name'].append({
                "use": "official",
                "family": name_parts[-1] if len(name_parts) > 1 else name_parts[0],
                "given": name_parts[:-1] if len(name_parts) > 1 else []
            })
        
        # 处理性别
        if user_profile.get('gender'):
            gender_map = {
                'male': 'male',
                'female': 'female',
                '男': 'male',
                '女': 'female',
                'other': 'other',
                '其他': 'other'
            }
            fhir_patient['gender'] = gender_map.get(user_profile['gender'].lower(), 'unknown')
        
        # 处理出生日期
        if user_profile.get('age'):
            # 如果只有年龄，估算出生年份
            birth_year = datetime.now().year - int(user_profile['age'])
            fhir_patient['birthDate'] = f"{birth_year}-01-01"
        elif user_profile.get('birthDate'):
            fhir_patient['birthDate'] = user_profile['birthDate']
        
        # 处理联系方式
        if user_profile.get('phone'):
            fhir_patient['telecom'].append({
                "system": "phone",
                "value": user_profile['phone'],
                "use": "mobile"
            })
        
        if user_profile.get('email'):
            fhir_patient['telecom'].append({
                "system": "email",
                "value": user_profile['email'],
                "use": "home"
            })
        
        # 处理地址（从session_data或user_profile获取）
        location = None
        if session_data and session_data.get('preferences', {}).get('preferred_city'):
            location = session_data['preferences']['preferred_city']
        elif user_profile.get('location'):
            location = user_profile['location']
        
        if location:
            # 解析地址信息
            address_parts = location.split('市')
            city = address_parts[0] + '市' if address_parts else location
            
            fhir_patient['address'].append({
                "use": "home",
                "type": "physical",
                "city": city,
                "country": "China"
            })
        
        # 处理婚姻状况
        if user_profile.get('maritalStatus'):
            marital_map = {
                'single': 'S',
                'married': 'M',
                'divorced': 'D',
                'widowed': 'W',
                '单身': 'S',
                '已婚': 'M',
                '离婚': 'D',
                '丧偶': 'W'
            }
            if user_profile['maritalStatus'].lower() in marital_map:
                fhir_patient['maritalStatus'] = {
                    "coding": [{
                        "system": "http://terminology.hl7.org/CodeSystem/v3-MaritalStatus",
                        "code": marital_map[user_profile['maritalStatus'].lower()],
                        "display": user_profile['maritalStatus']
                    }]
                }
        
        # 处理语言偏好
        fhir_patient['communication'] = [
            {
                "language": {
                    "coding": [{
                        "system": "urn:ietf:bcp:47",
                        "code": "zh",
                        "display": "Chinese"
                    }]
                },
                "preferred": True
            }
        ]
        
        # 添加扩展字段存储健康相关信息
        if user_profile.get('medical_history') or user_profile.get('health_concerns'):
            fhir_patient['extension'] = []
            
            # 医疗历史
            if user_profile.get('medical_history'):
                fhir_patient['extension'].append({
                    "url": "http://nutrirec.example.com/fhir/StructureDefinition/medical-history",
                    "valueString": json.dumps(user_profile['medical_history'], ensure_ascii=False)
                })
            
            # 健康关注点
            if user_profile.get('health_concerns'):
                fhir_patient['extension'].append({
                    "url": "http://nutrirec.example.com/fhir/StructureDefinition/health-concerns",
                    "valueString": json.dumps(user_profile['health_concerns'], ensure_ascii=False)
                })
        
        return fhir_patient
    
    def convert_from_fhir_patient(self, fhir_patient: Dict[str, Any]) -> Dict[str, Any]:
        """
        将FHIR R4 Patient资源转换回系统内部格式
        
        Args:
            fhir_patient: FHIR R4 Patient资源
            
        Returns:
            系统内部的user_profile格式
        """
        user_profile = {
            "user_id": fhir_patient.get('id'),
            "fhir_resource_type": "Patient"
        }
        
        # 提取姓名
        if fhir_patient.get('name') and len(fhir_patient['name']) > 0:
            name_data = fhir_patient['name'][0]
            given_names = ' '.join(name_data.get('given', []))
            family_name = name_data.get('family', '')
            user_profile['name'] = f"{given_names} {family_name}".strip()
        
        # 提取性别
        if fhir_patient.get('gender'):
            gender_map = {
                'male': '男',
                'female': '女',
                'other': '其他',
                'unknown': '未知'
            }
            user_profile['gender'] = gender_map.get(fhir_patient['gender'], fhir_patient['gender'])
        
        # 提取年龄/出生日期
        if fhir_patient.get('birthDate'):
            birth_date = datetime.strptime(fhir_patient['birthDate'], "%Y-%m-%d")
            age = datetime.now().year - birth_date.year
            user_profile['age'] = age
            user_profile['birthDate'] = fhir_patient['birthDate']
        
        # 提取联系方式
        for telecom in fhir_patient.get('telecom', []):
            if telecom['system'] == 'phone':
                user_profile['phone'] = telecom['value']
            elif telecom['system'] == 'email':
                user_profile['email'] = telecom['value']
        
        # 提取地址
        if fhir_patient.get('address') and len(fhir_patient['address']) > 0:
            address = fhir_patient['address'][0]
            location_parts = []
            if address.get('city'):
                location_parts.append(address['city'])
            if address.get('state'):
                location_parts.append(address['state'])
            if address.get('country'):
                location_parts.append(address['country'])
            if location_parts:
                user_profile['location'] = ''.join(location_parts)
        
        # 提取婚姻状况
        if fhir_patient.get('maritalStatus'):
            marital_coding = fhir_patient['maritalStatus'].get('coding', [])
            if marital_coding:
                marital_code = marital_coding[0].get('code')
                marital_map = {
                    'S': '单身',
                    'M': '已婚',
                    'D': '离婚',
                    'W': '丧偶'
                }
                user_profile['maritalStatus'] = marital_map.get(marital_code, marital_coding[0].get('display', ''))
        
        # 提取扩展字段
        for extension in fhir_patient.get('extension', []):
            if extension['url'] == "http://nutrirec.example.com/fhir/StructureDefinition/medical-history":
                try:
                    user_profile['medical_history'] = json.loads(extension['valueString'])
                except:
                    user_profile['medical_history'] = [extension['valueString']]
            elif extension['url'] == "http://nutrirec.example.com/fhir/StructureDefinition/health-concerns":
                try:
                    user_profile['health_concerns'] = json.loads(extension['valueString'])
                except:
                    user_profile['health_concerns'] = [extension['valueString']]
        
        return user_profile
    
    def create_fhir_observation(self, patient_id: str, observation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建FHIR Observation资源（用于记录健康指标）
        
        Args:
            patient_id: 患者ID
            observation_data: 观察数据（如血压、体重等）
            
        Returns:
            FHIR R4 Observation资源
        """
        observation = {
            "resourceType": "Observation",
            "id": str(uuid.uuid4()),
            "status": "final",
            "subject": {
                "reference": f"Patient/{patient_id}"
            },
            "effectiveDateTime": datetime.now().isoformat(),
            "issued": datetime.now().isoformat()
        }
        
        # 根据观察类型设置编码和值
        obs_type = observation_data.get('type', '').lower()
        
        if obs_type == 'weight' or '体重' in obs_type:
            observation['code'] = {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "29463-7",
                    "display": "Body weight"
                }]
            }
            observation['valueQuantity'] = {
                "value": observation_data.get('value'),
                "unit": "kg",
                "system": "http://unitsofmeasure.org",
                "code": "kg"
            }
        elif obs_type == 'height' or '身高' in obs_type:
            observation['code'] = {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "8302-2",
                    "display": "Body height"
                }]
            }
            observation['valueQuantity'] = {
                "value": observation_data.get('value'),
                "unit": "cm",
                "system": "http://unitsofmeasure.org",
                "code": "cm"
            }
        elif obs_type == 'blood_pressure' or '血压' in obs_type:
            observation['code'] = {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": "85354-9",
                    "display": "Blood pressure panel"
                }]
            }
            # 血压需要组件
            observation['component'] = [
                {
                    "code": {
                        "coding": [{
                            "system": "http://loinc.org",
                            "code": "8480-6",
                            "display": "Systolic blood pressure"
                        }]
                    },
                    "valueQuantity": {
                        "value": observation_data.get('systolic'),
                        "unit": "mmHg",
                        "system": "http://unitsofmeasure.org",
                        "code": "mm[Hg]"
                    }
                },
                {
                    "code": {
                        "coding": [{
                            "system": "http://loinc.org",
                            "code": "8462-4",
                            "display": "Diastolic blood pressure"
                        }]
                    },
                    "valueQuantity": {
                        "value": observation_data.get('diastolic'),
                        "unit": "mmHg",
                        "system": "http://unitsofmeasure.org",
                        "code": "mm[Hg]"
                    }
                }
            ]
        
        return observation
    
    def create_fhir_condition(self, patient_id: str, condition_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        创建FHIR Condition资源（用于记录疾病/健康状况）
        
        Args:
            patient_id: 患者ID
            condition_data: 疾病/状况数据
            
        Returns:
            FHIR R4 Condition资源
        """
        condition = {
            "resourceType": "Condition",
            "id": str(uuid.uuid4()),
            "clinicalStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": condition_data.get('status', 'active')
                }]
            },
            "subject": {
                "reference": f"Patient/{patient_id}"
            },
            "recordedDate": datetime.now().isoformat()
        }
        
        # 设置疾病编码
        if condition_data.get('code'):
            condition['code'] = {
                "coding": [{
                    "system": condition_data.get('system', 'http://snomed.info/sct'),
                    "code": condition_data['code'],
                    "display": condition_data.get('display', '')
                }],
                "text": condition_data.get('text', condition_data.get('display', ''))
            }
        elif condition_data.get('text'):
            # 如果没有标准编码，只使用文本描述
            condition['code'] = {
                "text": condition_data['text']
            }
        
        # 设置发病日期
        if condition_data.get('onsetDate'):
            condition['onsetDateTime'] = condition_data['onsetDate']
        
        return condition

# 使用示例
if __name__ == "__main__":
    converter = FHIRDataConverter()
    
    # 示例：转换用户配置为FHIR Patient
    user_profile = {
        "user_id": "user123",
        "name": "张三",
        "age": 35,
        "gender": "男",
        "phone": "+86-13800138000",
        "email": "zhangsan@example.com",
        "location": "广州市天河区",
        "medical_history": ["高血压", "糖尿病"],
        "health_concerns": ["体重管理", "血糖控制"]
    }
    
    fhir_patient = converter.convert_to_fhir_patient(user_profile)
    print("FHIR Patient Resource:")
    print(json.dumps(fhir_patient, indent=2, ensure_ascii=False))
    
    # 示例：转换回系统格式
    converted_back = converter.convert_from_fhir_patient(fhir_patient)
    print("\nConverted back to internal format:")
    print(json.dumps(converted_back, indent=2, ensure_ascii=False))