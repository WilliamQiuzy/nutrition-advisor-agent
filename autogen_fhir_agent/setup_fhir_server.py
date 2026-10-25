#!/usr/bin/env python3
"""
FHIR服务器快速设置脚本
帮助用户快速部署和配置FHIR服务器
"""

import os
import json
import requests
import subprocess
import time
from typing import Dict, Any, Optional

def print_banner():
    """打印欢迎横幅"""
    print("=" * 80)
    print("🏥 NutriRec医疗AI - FHIR服务器快速设置工具")
    print("=" * 80)

def check_docker():
    """检查Docker是否安装"""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True, check=True)
        print(f"✅ Docker已安装: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Docker未安装，请先安装Docker")
        print("   下载地址: https://www.docker.com/products/docker-desktop")
        return False

def create_docker_compose():
    """创建docker-compose.yml文件"""
    compose_content = """version: '3.8'

services:
  # HAPI FHIR服务器
  hapi-fhir:
    image: hapiproject/hapi:latest
    container_name: nutrirec-fhir-server
    ports:
      - "8080:8080"
    environment:
      # 数据库配置
      - spring.datasource.url=jdbc:postgresql://fhir-db:5432/hapi
      - spring.datasource.username=hapi
      - spring.datasource.password=HapiPassword123
      - spring.datasource.driverClassName=org.postgresql.Driver
      - spring.jpa.database-platform=org.hibernate.dialect.PostgreSQL10Dialect
      
      # FHIR配置
      - hapi.fhir.default_encoding=json
      - hapi.fhir.default_pretty_print=true
      - hapi.fhir.default_page_size=20
      - hapi.fhir.max_page_size=200
      - hapi.fhir.server_address=http://localhost:8080/fhir/
      
      # 启用搜索功能
      - hapi.fhir.allow_multiple_delete=true
      - hapi.fhir.reuse_cached_search_results_millis=60000
      
      # 日志配置
      - logging.level.ca.uhn.fhir.jpa=INFO
      
    depends_on:
      - fhir-db
    volumes:
      - hapi_lucene_data:/data/hapi/lucenefiles
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/fhir/metadata"]
      interval: 30s
      timeout: 10s
      retries: 5

  # PostgreSQL数据库
  fhir-db:
    image: postgres:13
    container_name: nutrirec-fhir-db
    environment:
      - POSTGRES_DB=hapi
      - POSTGRES_USER=hapi
      - POSTGRES_PASSWORD=HapiPassword123
    volumes:
      - fhir_db_data:/var/lib/postgresql/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hapi"]
      interval: 30s
      timeout: 10s
      retries: 5

  # Redis缓存 (可选，提升性能)
  redis:
    image: redis:6-alpine
    container_name: nutrirec-fhir-redis
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

volumes:
  fhir_db_data:
    driver: local
  hapi_lucene_data:
    driver: local
  redis_data:
    driver: local

networks:
  default:
    name: nutrirec-fhir-network
"""
    
    with open('docker-compose.yml', 'w', encoding='utf-8') as f:
        f.write(compose_content)
    
    print("✅ 已创建 docker-compose.yml 文件")

def create_env_file():
    """创建环境变量文件"""
    env_content = """# NutriRec医疗AI - FHIR服务器配置

# FHIR服务器配置
FHIR_BASE_URL=http://localhost:8080/fhir/
FHIR_CLIENT_ID=nutrirec-medical-ai
FHIR_CLIENT_SECRET=change-me
USE_FHIR_FORMAT=true

# 数据库配置
FHIR_DB_HOST=localhost
FHIR_DB_PORT=5432
FHIR_DB_NAME=hapi
FHIR_DB_USER=hapi
FHIR_DB_PASSWORD=HapiPassword123

# NutriRec扩展定义URL
NUTRIREC_MEDICAL_HISTORY_URL=http://nutrirec.example.com/fhir/StructureDefinition/medical-history
NUTRIREC_CURRENT_SYMPTOMS_URL=http://nutrirec.example.com/fhir/StructureDefinition/current-symptoms
NUTRIREC_PATIENT_PREFERENCES_URL=http://nutrirec.example.com/fhir/StructureDefinition/patient-preferences

# 安全配置
FHIR_ENABLE_CORS=true
FHIR_ENABLE_SECURITY=false  # 开发环境设为false，生产环境应设为true
"""
    
    with open('.env.fhir', 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print("✅ 已创建 .env.fhir 环境配置文件")

def start_fhir_server():
    """启动FHIR服务器"""
    print("\n🚀 正在启动FHIR服务器...")
    print("这可能需要几分钟时间，请耐心等待...")
    
    try:
        # 启动服务
        subprocess.run(['docker-compose', 'up', '-d'], check=True)
        print("✅ FHIR服务器已启动")
        
        # 等待服务器就绪
        print("\n⏳ 等待服务器启动完成...")
        max_attempts = 30
        for attempt in range(max_attempts):
            try:
                response = requests.get('http://localhost:8080/fhir/metadata', timeout=5)
                if response.status_code == 200:
                    print("✅ FHIR服务器已就绪！")
                    return True
            except requests.exceptions.RequestException:
                pass
            
            print(f"   尝试 {attempt + 1}/{max_attempts}...")
            time.sleep(10)
        
        print("⚠️ 服务器启动超时，请检查日志: docker-compose logs")
        return False
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 启动失败: {e}")
        return False

def test_fhir_server():
    """测试FHIR服务器功能"""
    print("\n🧪 测试FHIR服务器功能...")
    
    base_url = "http://localhost:8080/fhir"
    
    # 1. 测试服务器元数据
    try:
        response = requests.get(f"{base_url}/metadata")
        if response.status_code == 200:
            print("✅ 服务器元数据获取成功")
        else:
            print(f"❌ 元数据获取失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
    
    # 2. 创建测试患者
    test_patient = {
        "resourceType": "Patient",
        "identifier": [
            {
                "system": "http://nutrirec.example.com/patient-id",
                "value": "test-patient-001",
                "use": "official"
            }
        ],
        "active": True,
        "name": [
            {
                "use": "official",
                "family": "张",
                "given": ["测试"]
            }
        ],
        "gender": "female",
        "birthDate": "1980-01-01",
        "address": [
            {
                "use": "home",
                "city": "北京市",
                "country": "China"
            }
        ],
        "extension": [
            {
                "url": "http://nutrirec.example.com/fhir/StructureDefinition/medical-history",
                "valueString": '["高血压", "糖尿病"]'
            }
        ]
    }
    
    try:
        response = requests.post(
            f"{base_url}/Patient",
            json=test_patient,
            headers={"Content-Type": "application/fhir+json"}
        )
        
        if response.status_code in [200, 201]:
            patient_data = response.json()
            patient_id = patient_data.get('id')
            print(f"✅ 测试患者创建成功，ID: {patient_id}")
            
            # 3. 测试患者查询
            response = requests.get(f"{base_url}/Patient/{patient_id}")
            if response.status_code == 200:
                print("✅ 患者数据查询成功")
                return True
            else:
                print(f"❌ 患者查询失败: {response.status_code}")
                return False
        else:
            print(f"❌ 患者创建失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def create_structure_definitions():
    """创建NutriRec医疗的自定义扩展定义"""
    print("\n📋 创建NutriRec医疗自定义扩展定义...")
    
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
        "description": "用于存储患者既往病史的扩展",
        "differential": {
            "element": [
                {
                    "id": "Extension.value[x]",
                    "path": "Extension.value[x]",
                    "type": [{"code": "string"}],
                    "definition": "患者病史，JSON字符串格式"
                }
            ]
        }
    }
    
    # 当前症状扩展定义
    current_symptoms_def = {
        "resourceType": "StructureDefinition", 
        "url": "http://nutrirec.example.com/fhir/StructureDefinition/current-symptoms",
        "name": "NutriRecCurrentSymptoms",
        "title": "NutriRec医疗当前症状扩展",
        "status": "active",
        "kind": "complex-type",
        "abstract": False,
        "type": "Extension",
        "baseDefinition": "http://hl7.org/fhir/StructureDefinition/Extension",
        "derivation": "constraint",
        "description": "用于存储患者当前症状的扩展",
        "differential": {
            "element": [
                {
                    "id": "Extension.value[x]",
                    "path": "Extension.value[x]",
                    "type": [{"code": "string"}],
                    "definition": "患者当前症状，JSON字符串格式"
                }
            ]
        }
    }
    
    # 保存定义文件
    with open('nutrirec-medical-history-extension.json', 'w', encoding='utf-8') as f:
        json.dump(medical_history_def, f, ensure_ascii=False, indent=2)
    
    with open('nutrirec-current-symptoms-extension.json', 'w', encoding='utf-8') as f:
        json.dump(current_symptoms_def, f, ensure_ascii=False, indent=2)
    
    print("✅ 扩展定义文件已创建:")
    print("   - nutrirec-medical-history-extension.json")
    print("   - nutrirec-current-symptoms-extension.json")

def show_usage_info():
    """显示使用说明"""
    print("\n" + "=" * 80)
    print("🎉 FHIR服务器设置完成！")
    print("=" * 80)
    
    print("\n📋 服务信息:")
    print("   🌐 FHIR服务器: http://localhost:8080/fhir/")
    print("   📊 管理界面: http://localhost:8080/")
    print("   🗄️ 数据库: PostgreSQL (端口5432)")
    
    print("\n🔧 常用命令:")
    print("   查看服务状态: docker-compose ps")
    print("   查看日志:     docker-compose logs")
    print("   停止服务:     docker-compose down")
    print("   重启服务:     docker-compose restart")
    
    print("\n📚 API示例:")
    print("   获取元数据:   curl http://localhost:8080/fhir/metadata")
    print("   搜索患者:     curl http://localhost:8080/fhir/Patient")
    print("   创建患者:     curl -X POST -H 'Content-Type: application/fhir+json' \\")
    print("                      -d @patient.json http://localhost:8080/fhir/Patient")
    
    print("\n💡 下一步:")
    print("   1. 更新您的NutriRec系统配置文件 (.env)")
    print("   2. 重启NutriRec医疗AI系统")
    print("   3. 测试FHIR集成功能")

def main():
    """主函数"""
    print_banner()
    
    # 检查Docker
    if not check_docker():
        return
    
    print("\n🔧 开始设置FHIR服务器...")
    
    # 创建配置文件
    create_docker_compose()
    create_env_file()
    create_structure_definitions()
    
    # 询问是否启动服务器
    start_server = input("\n❓ 是否现在启动FHIR服务器？(y/n): ").lower().strip()
    
    if start_server in ['y', 'yes', '是']:
        if start_fhir_server():
            if test_fhir_server():
                show_usage_info()
            else:
                print("\n⚠️ 服务器测试失败，请检查配置")
        else:
            print("\n❌ 服务器启动失败")
    else:
        print("\n📝 配置文件已创建，您可以稍后运行以下命令启动服务器:")
        print("   docker-compose up -d")

if __name__ == "__main__":
    main() 