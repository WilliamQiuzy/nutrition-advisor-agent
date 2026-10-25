#!/usr/bin/env python3
"""
FHIR服务器设置演示 - 简化版
演示如何设置和配置FHIR服务器（无需实际网络连接）
"""

import os
import json

def print_banner():
    """打印欢迎横幅"""
    print("=" * 80)
    print("🏥 NutriRec医疗AI - FHIR服务器设置演示")
    print("=" * 80)

def demonstrate_fhir_concepts():
    """演示FHIR相关概念"""
    print("\n📚 FHIR核心概念解释:")
    print("-" * 50)
    
    print("\n1️⃣ FHIR Client的作用:")
    print("   🔗 连接应用程序与FHIR服务器")
    print("   📊 标准化医疗数据交换")
    print("   🔒 处理身份验证和安全")
    print("   📋 管理患者、观察、诊断等资源")
    
    print("\n2️⃣ FHIR服务器的功能:")
    print("   💾 存储医疗健康数据")
    print("   🌐 提供RESTful API接口")
    print("   🔍 支持复杂的医疗数据查询")
    print("   🔄 确保不同系统间的互操作性")

def explain_structure_definition_url():
    """解释StructureDefinition URL"""
    print("\n3️⃣ StructureDefinition URL解析:")
    print("-" * 50)
    
    url = "http://nutrirec.example.com/fhir/StructureDefinition/medical-history"
    print(f"🔗 示例URL: {url}")
    print()
    print("URL结构分解:")
    print("┌─ http://nutrirec.example.com  ← 您的组织域名空间")
    print("├─ /fhir/StructureDefinition ← FHIR标准路径")
    print("└─ /medical-history         ← 扩展名称")
    print()
    print("🎯 作用:")
    print("   • 定义自定义的数据结构扩展")
    print("   • 确保不同组织的扩展不冲突")
    print("   • 提供标准化的数据格式")

def create_sample_structure_definition():
    """创建示例扩展定义"""
    print("\n4️⃣ 创建NutriRec医疗自定义扩展定义:")
    print("-" * 50)
    
    # 病史扩展定义
    medical_history_def = {
        "resourceType": "StructureDefinition",
        "url": "http://nutrirec.example.com/fhir/StructureDefinition/medical-history",
        "name": "NutriRecMedicalHistory",
        "title": "NutriRec医疗病史扩展",
        "status": "active",
        "kind": "complex-type",
        "abstract": False,
        "type": "Extension",
        "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Extension",
        "derivation": "constraint",
        "description": "用于存储患者既往病史的扩展字段",
        "differential": {
            "element": [
                {
                    "id": "Extension.value[x]",
                    "path": "Extension.value[x]",
                    "type": [{"code": "string"}],
                    "definition": "患者病史信息，以JSON字符串格式存储"
                }
            ]
        }
    }
    
    # 保存到文件
    with open('nutrirec-medical-history-extension.json', 'w', encoding='utf-8') as f:
        json.dump(medical_history_def, f, ensure_ascii=False, indent=2)
    
    print("✅ 已创建扩展定义文件: nutrirec-medical-history-extension.json")
    
    # 显示部分内容
    print("\n📄 扩展定义内容预览:")
    print(json.dumps(medical_history_def, ensure_ascii=False, indent=2)[:500] + "...")

def create_sample_patient_with_extension():
    """创建使用扩展的示例患者数据"""
    print("\n5️⃣ 使用扩展的患者数据示例:")
    print("-" * 50)
    
    sample_patient = {
        "resourceType": "Patient",
        "id": "nutrirec-patient-001",
        "identifier": [
            {
                "system": "http://nutrirec.example.com/patient-id",
                "value": "nutrirec-patient-001",
                "use": "official"
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "family": "张",
                "given": ["女士"]
            }
        ],
        "gender": "female",
        "birthDate": "1972-01-01",
        "address": [
            {
                "use": "home",
                "city": "北京市",
                "country": "China"
            }
        ],
        # 这里使用我们的自定义扩展
        "extension": [
            {
                "url": "http://nutrirec.example.com/fhir/StructureDefinition/medical-history",
                "valueString": '["高血压", "糖尿病", "心脏病"]'
            },
            {
                "url": "http://nutrirec.example.com/fhir/StructureDefinition/current-symptoms",
                "valueString": '["头痛", "失眠", "胸闷"]'
            }
        ]
    }
    
    # 保存示例
    with open('sample-patient-with-extensions.json', 'w', encoding='utf-8') as f:
        json.dump(sample_patient, f, ensure_ascii=False, indent=2)
    
    print("✅ 已创建患者示例文件: sample-patient-with-extensions.json")
    
    # 显示扩展部分
    print("\n📋 患者扩展数据:")
    for ext in sample_patient["extension"]:
        url = ext["url"]
        value = ext["valueString"]
        if "medical-history" in url:
            print(f"   🏥 既往病史: {value}")
        elif "current-symptoms" in url:
            print(f"   🤒 当前症状: {value}")

def show_deployment_options():
    """显示部署选项"""
    print("\n6️⃣ FHIR服务器部署选项:")
    print("-" * 50)
    
    print("\n🌟 推荐方案:")
    
    print("\n🔸 开发/测试环境:")
    print("   • HAPI FHIR (Docker) - 免费开源")
    print("   • 公共测试服务器 - https://hapi.fhir.org/baseR4/")
    print("   • 成本: $0")
    
    print("\n🔸 小型生产环境:")
    print("   • 阿里云/腾讯云 VPS + HAPI FHIR")
    print("   • 配置: 2核4G，50GB存储")
    print("   • 成本: ¥200-500/月")
    
    print("\n🔸 中大型生产环境:")
    print("   • Azure FHIR Service")
    print("   • Google Cloud Healthcare API")
    print("   • AWS HealthLake")
    print("   • 成本: $200-2000/月")

def create_docker_compose_sample():
    """创建Docker Compose示例"""
    print("\n7️⃣ Docker部署配置:")
    print("-" * 50)
    
    compose_content = """version: '3.8'

services:
  # HAPI FHIR服务器
  nutrirec-fhir:
    image: hapiproject/hapi:latest
    container_name: nutrirec-fhir-server
    ports:
      - "8080:8080"
    environment:
      - spring.datasource.url=jdbc:postgresql://fhir-db:5432/hapi
      - spring.datasource.username=hapi
      - spring.datasource.password=HapiPassword123
      - hapi.fhir.server_address=http://localhost:8080/fhir/
    depends_on:
      - fhir-db
    restart: unless-stopped

  # PostgreSQL数据库
  fhir-db:
    image: postgres:13
    environment:
      - POSTGRES_DB=hapi
      - POSTGRES_USER=hapi
      - POSTGRES_PASSWORD=HapiPassword123
    volumes:
      - fhir_data:/var/lib/postgresql/data
    restart: unless-stopped

volumes:
  fhir_data:
"""
    
    with open('docker-compose.fhir.yml', 'w', encoding='utf-8') as f:
        f.write(compose_content)
    
    print("✅ 已创建Docker配置: docker-compose.fhir.yml")
    print("\n🚀 启动命令:")
    print("   docker-compose -f docker-compose.fhir.yml up -d")

def create_integration_example():
    """创建集成示例"""
    print("\n8️⃣ NutriRec系统集成示例:")
    print("-" * 50)
    
    integration_code = '''
# NutriRec医疗AI系统 - FHIR集成配置

# 1. 环境变量配置 (.env文件)
FHIR_BASE_URL=http://localhost:8080/fhir/
FHIR_CLIENT_ID=nutrirec-medical-ai
USE_FHIR_FORMAT=true

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
'''
    
    with open('nutrirec_fhir_integration_example.py', 'w', encoding='utf-8') as f:
        f.write(integration_code)
    
    print("✅ 已创建集成示例: nutrirec_fhir_integration_example.py")

def show_next_steps():
    """显示后续步骤"""
    print("\n" + "=" * 80)
    print("🎉 FHIR设置演示完成！")
    print("=" * 80)
    
    print("\n📋 已创建的文件:")
    print("   📄 nutrirec-medical-history-extension.json - 扩展定义")
    print("   👤 sample-patient-with-extensions.json - 患者示例")
    print("   🐳 docker-compose.fhir.yml - Docker配置")
    print("   🔧 nutrirec_fhir_integration_example.py - 集成示例")
    
    print("\n🚀 下一步操作建议:")
    print("   1️⃣ 选择合适的FHIR服务器方案")
    print("   2️⃣ 部署FHIR服务器 (推荐先用Docker测试)")
    print("   3️⃣ 创建您的自定义扩展定义")
    print("   4️⃣ 更新NutriRec系统的FHIR配置")
    print("   5️⃣ 测试患者数据的创建和查询")
    
    print("\n💡 快速测试命令:")
    print("   # 启动FHIR服务器")
    print("   docker-compose -f docker-compose.fhir.yml up -d")
    print("   ")
    print("   # 测试服务器")
    print("   curl http://localhost:8080/fhir/metadata")
    print("   ")
    print("   # 创建测试患者")
    print("   curl -X POST -H 'Content-Type: application/fhir+json' \\")
    print("        -d @sample-patient-with-extensions.json \\")
    print("        http://localhost:8080/fhir/Patient")

def main():
    """主函数"""
    print_banner()
    
    # 演示各个概念
    demonstrate_fhir_concepts()
    explain_structure_definition_url()
    create_sample_structure_definition()
    create_sample_patient_with_extension()
    show_deployment_options()
    create_docker_compose_sample()
    create_integration_example()
    show_next_steps()

if __name__ == "__main__":
    main() 