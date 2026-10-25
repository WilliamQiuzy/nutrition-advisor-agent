# NutriRec医疗知识库

本文件夹包含NutriRec医疗保健品推荐AI系统的所有知识库文件。

## 文件结构

### 1. clinics.csv - NutriRec线下门诊信息
**文件位置**: `knowledge_base/clinics.csv`
**Headers**:
- 城市
- 门诊名称
- 门诊名称英文翻译
- 核心科室
- 服务内容
- 营业时间
- 门诊电话
- 门诊地址
- 地址英文翻译
- 免费停车券

**用途**: 为用户提供准确的就诊指引，匹配合适的科室和门诊

### 2. supplement_docs.csv - 合作商城保健品信息
**文件位置**: `knowledge_base/supplement_docs.csv`
**Headers**:
- 商品名
- 链接
- 商品简介/功效
- 商品用量用法
- 商品成分
- 商品忌口/限制
- 商品标签

**用途**: 推荐NutriRec甄选的保健品，提供详细的产品信息

### 3. nutrirec_qa.csv - NutriRec问答语料库
**文件位置**: `knowledge_base/nutrirec_qa.csv`
**Headers**:
- 序号
- 问题
- 回答

**用途**: 提供标准化的医疗问答，确保回答的准确性和一致性

## 集成说明

这些CSV文件将通过 `knowledge_manager.py` 模块加载和管理，供各个智能体调用。

## 更新流程

1. 将新的CSV文件放入此文件夹
2. 重启AI系统以加载最新数据
3. 系统会自动索引和缓存知识库内容