
# NutriRec医疗AI系统 - FHIR集成配置

# 1. 环境变量配置 (.env文件)
# FHIR_BASE_URL=http://localhost:8080/fhir/
# FHIR_CLIENT_ID=nutrirec-medical-ai
# USE_FHIR_FORMAT=true

# 2. Python集成代码示例
import requests
import json

class NutriRecFHIRClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        
    def create_patient(self, patient_data):
        """创建患者记录"""
        url = f"{self.base_url}/Patient"
        headers = {"Content-Type": "application/fhir+json"}
        response = requests.post(url, json=patient_data, headers=headers)
        return response.json() if response.status_code in [200, 201] else None
    
    def search_patients(self, name=None, city=None):
        """搜索患者"""
        url = f"{self.base_url}/Patient"
        params = {}
        if name:
            params['name'] = name
        if city:
            params['address-city'] = city
        
        response = requests.get(url, params=params)
        return response.json() if response.status_code == 200 else None

# 3. 使用示例
client = NutriRecFHIRClient("http://localhost:8080/fhir")

# 创建患者
patient = client.create_patient({
    "resourceType": "Patient",
    "name": [{"family": "张", "given": ["三"]}],
    "extension": [{
        "url": "http://nutrirec.example.com/fhir/StructureDefinition/medical-history",
        "valueString": '["高血压"]'
    }]
})

print(f"患者创建成功，ID: {patient['id']}")
