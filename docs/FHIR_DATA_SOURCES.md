# FHIR医疗数据源配置指南

## 📊 数据来源概述

你的保健品推荐AI系统可以从以下FHIR服务器获取真实的医疗数据：

### 🏥 主要数据源：HAPI FHIR演示服务器

**服务器信息：**
- **URL**: `https://hapi.fhir.org/baseR4`
- **类型**: 公开的FHIR R4测试服务器
- **认证**: 无需认证
- **数据规模**: 300万+患者记录，430万+观察记录
- **更新频率**: 定期更新
- **费用**: 完全免费

**数据内容：**
- ✅ 患者基本信息（姓名、性别、生日、联系方式）
- ✅ 疾病诊断记录（ICD-10编码）
- ✅ 用药记录（处方药、剂量、频次）
- ✅ 实验室检查结果（血液、尿液、生化指标）
- ✅ 生命体征（血压、心率、体温、体重）
- ✅ 过敏史和不良反应
- ✅ 就诊记录和医生诊断

## 🔧 配置方法

### 1. 环境变量配置

在你的 `.env` 文件中设置：

```env
# FHIR服务器配置
FHIR_BASE_URL=https://hapi.fhir.org/baseR4
FHIR_CLIENT_ID=healthcare_ai_agent
FHIR_CLIENT_SECRET=  # 演示服务器不需要

# FHIR MCP服务器配置
FHIR_MCP_FHIR__BASE_URL=https://hapi.fhir.org/baseR4
FHIR_MCP_FHIR__ACCESS_TOKEN=  # 不需要令牌
FHIR_MCP_FHIR__TIMEOUT=30
```

### 2. 代码中的使用示例

```python
from shared.fhir_client import FHIRClient, FHIRConfig

# 创建FHIR配置
fhir_config = FHIRConfig(
    base_url="https://hapi.fhir.org/baseR4",
    client_id="healthcare_ai_agent",
    client_secret=None  # 演示服务器不需要
)

# 初始化客户端
fhir_client = FHIRClient(fhir_config)

# 获取患者数据
patient_data = await fhir_client.get_comprehensive_patient_data("597309")
```

## 🎯 推荐测试患者

基于我们的测试，以下患者ID有丰富的医疗数据，适合用于AI分析：

- **患者ID**: `597309` （推荐，有8条完整记录）
- **患者ID**: `597296` （基础数据，有观察记录）
- **患者ID**: `597297` （包含基本信息）

## 🌐 其他可用数据源

### 2. SMART Health IT 测试服务器（备选）

```env
FHIR_BASE_URL=https://r4.smarthealthit.org
```

**特点：**
- 支持SMART on FHIR认证
- 更真实的临床环境模拟
- 需要OAuth2认证流程

### 3. 本地FHIR服务器（生产环境）

```env
FHIR_BASE_URL=http://localhost:8080/fhir
```

**使用场景：**
- 生产环境部署
- 私有医疗数据
- 完全控制数据访问

## 📋 数据结构示例

### 患者基本信息
```json
{
  "id": "597309",
  "name": [{"given": ["John"], "family": "Doe"}],
  "gender": "male",
  "birthDate": "1990-05-15",
  "address": [{"city": "Boston", "state": "MA"}]
}
```

### 疾病记录
```json
{
  "code": {
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "38341003",
      "display": "Hypertension"
    }]
  },
  "clinicalStatus": "active"
}
```

### 用药记录
```json
{
  "medicationCodeableConcept": {
    "text": "Lisinopril 10mg"
  },
  "dosageInstruction": [{
    "text": "Take one tablet daily"
  }]
}
```

### 实验室结果
```json
{
  "code": {
    "coding": [{
      "code": "33747-0",
      "display": "Cholesterol, Total"
    }]
  },
  "valueQuantity": {
    "value": 180,
    "unit": "mg/dL"
  }
}
```

## 🔍 数据查询示例

### 1. 搜索特定条件的患者
```
GET https://hapi.fhir.org/baseR4/Patient?gender=male&_count=10
```

### 2. 获取患者的所有疾病
```
GET https://hapi.fhir.org/baseR4/Condition?patient=597309
```

### 3. 获取患者的用药记录
```
GET https://hapi.fhir.org/baseR4/MedicationRequest?patient=597309
```

### 4. 获取实验室检查结果
```
GET https://hapi.fhir.org/baseR4/Observation?patient=597309&category=laboratory
```

## 🛡️ 数据安全和隐私

### 演示服务器数据特点：
- ✅ 匿名化的测试数据
- ✅ 符合FHIR标准格式
- ✅ 无真实患者隐私风险
- ✅ 适合开发和测试用途

### 生产环境注意事项：
- 🔒 必须遵守HIPAA等医疗隐私法规
- 🔒 实施适当的访问控制
- 🔒 加密传输和存储
- 🔒 审计日志记录

## 🚀 快速开始

1. **测试连接**：
   ```bash
   python simple_fhir_test.py
   ```

2. **验证配置**：
   ```bash
   curl "https://hapi.fhir.org/baseR4/Patient/597309"
   ```

3. **启动AI系统**：
   ```python
   from autogen_fhir_agent.agents import get_supplement_system
   
   system = get_supplement_system()
   result = await system.run_comprehensive_supplement_consultation("597309")
   ```

## 📚 相关资源

- [HAPI FHIR服务器文档](https://hapifhir.io/)
- [FHIR R4规范](https://hl7.org/fhir/R4/)
- [SMART on FHIR指南](https://docs.smarthealthit.org/)
- [Web界面](https://hapi.fhir.org/resource?serverId=home_r4)

---

**总结**: 你的系统已经配置为使用HAPI FHIR演示服务器，这提供了数百万条真实的医疗测试数据，完全免费且无需认证，非常适合开发和测试你的保健品推荐AI系统！🎯 