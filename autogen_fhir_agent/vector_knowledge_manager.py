#!/usr/bin/env python3
"""
NutriRec医疗向量化知识库管理器
实现工业级向量检索和RAG系统
"""

import pandas as pd
import numpy as np
import os
import json
import asyncio
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import logging
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import hashlib
import pickle
import time
from datetime import datetime
from functools import lru_cache
import threading

# 向量检索依赖
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    logging.warning("FAISS not available, using fallback similarity search")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logging.warning("sentence-transformers not available, using OpenAI embeddings")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import jieba
    import jieba.analyse
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logging.warning("jieba not available, Chinese text processing will be limited")

logger = logging.getLogger(__name__)

# 性能优化参数
EMBEDDING_BATCH_SIZE = 64  # 批量编码大小
MAX_WORKERS = 4  # 并行工作线程数
CACHE_SIZE = 10000  # LRU缓存大小
IVF_THRESHOLD = 1000  # 使用IVF索引的阈值

@dataclass
class SearchResult:
    """搜索结果数据结构"""
    content: str
    metadata: Dict[str, Any]
    score: float
    source: str
    chunk_id: str

@dataclass
class VectorIndexConfig:
    """向量索引配置"""
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dimension: int = 384
    chunk_size: int = 512
    chunk_overlap: int = 50
    similarity_threshold: float = 0.3  # 降低阈值以提高召回率
    max_results: int = 5
    use_faiss: bool = True
    faiss_index_type: str = "IVF"  # IVF, HNSW, Flat
    cache_embeddings: bool = True

@dataclass
class UserLocationContext:
    """用户位置上下文"""
    current_city: Optional[str] = None
    preferred_cities: Optional[List[str]] = None
    location_source: str = "unknown"  # manual, ip, query, default
    confidence: float = 0.0
    last_updated: Optional[str] = None

@dataclass
class FHIRPatientContext:
    """FHIR患者上下文"""
    patient_id: Optional[str] = None
    fhir_patient_data: Optional[Dict[str, Any]] = None
    last_synced: Optional[str] = None
    sync_status: str = "pending"  # "pending", "synced", "failed"

class SmartLocationManager:
    """智能位置管理器 - 支持多种位置获取方式"""
    
    def __init__(self):
        self.user_context = UserLocationContext()
        self.location_inference_patterns = {
            # 明确位置指示词
            'explicit_patterns': [
                r'我在(.{2,4})',
                r'(.{2,4})这边',
                r'(.{2,4})这里',
                r'本地',
                r'附近',
                r'周边'
            ],
            # 隐含位置指示词
            'implicit_patterns': [
                r'就近',
                r'方便',
                r'离我近',
                r'不远的'
            ]
        }
    
    def set_user_location(self, city: str, source: str = "manual", confidence: float = 1.0):
        """手动设置用户位置"""
        self.user_context.current_city = city
        self.user_context.location_source = source
        self.user_context.confidence = confidence
        self.user_context.last_updated = pd.Timestamp.now().isoformat()
        logger.info(f"用户位置设定为: {city} (来源: {source}, 置信度: {confidence})")
    
    def infer_location_from_query(self, query: str) -> Optional[str]:
        """从查询中推断用户位置意图"""
        import re
        
        # 检查明确的位置指示
        for pattern in self.location_inference_patterns['explicit_patterns']:
            match = re.search(pattern, query)
            if match:
                inferred_city = match.group(1) if match.groups() else None
                if inferred_city and len(inferred_city) <= 4:  # 合理的城市名长度
                    return inferred_city
        
        # 检查隐含的位置需求
        for pattern in self.location_inference_patterns['implicit_patterns']:
            if re.search(pattern, query):
                # 有位置需求但没明确城市，返回当前位置
                return self.user_context.current_city
        
        return None
    
    def get_effective_location(self, query: str) -> Dict[str, Any]:
        """获取有效的位置信息"""
        # 1. 首先从查询中提取明确的城市
        explicit_cities = self._extract_cities_from_query(query)
        if explicit_cities:
            return {
                'city': explicit_cities[0],
                'source': 'query_explicit',
                'confidence': 1.0,
                'reasoning': f'查询中明确提到: {explicit_cities[0]}'
            }
        
        # 2. 推断隐含的位置需求
        inferred_city = self.infer_location_from_query(query)
        if inferred_city:
            return {
                'city': inferred_city,
                'source': 'query_inferred',
                'confidence': 0.8,
                'reasoning': '从查询语境推断位置需求'
            }
        
        # 3. 使用用户设定的当前位置
        if self.user_context.current_city:
            return {
                'city': self.user_context.current_city,
                'source': self.user_context.location_source,
                'confidence': self.user_context.confidence,
                'reasoning': f'使用用户设定位置: {self.user_context.current_city}'
            }
        
        # 4. 无位置信息
        return {
            'city': None,
            'source': 'none',
            'confidence': 0.0,
            'reasoning': '无位置信息，使用全局搜索'
        }
    
    def _extract_cities_from_query(self, query: str) -> List[str]:
        """从查询中提取城市名称"""
        cities = ['北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安', 
                 '南京', '天津', '重庆', '苏州', '长沙', '郑州', '青岛', '大连',
                 '宁波', '厦门', '福州', '济南', '合肥', '昆明', '海口', '东莞',
                 '佛山', '汕头', '珠海', '中山', '惠州', '江门', '湛江', '茂名']
        
        return [city for city in cities if city in query]
    
    def suggest_location_setup(self, available_cities: List[str]) -> Dict[str, Any]:
        """建议用户设置位置"""
        return {
            'message': '为了提供更精准的本地化推荐，建议设置您的位置',
            'available_cities': available_cities,
            'setup_methods': [
                {'method': 'manual', 'description': '手动选择城市', 'accuracy': 'high'},
                {'method': 'ip', 'description': 'IP地址定位', 'accuracy': 'medium'},
                {'method': 'query', 'description': '从对话中推断', 'accuracy': 'low'}
            ]
        }


# 工具函数
def _safe_async_run(coro_func, *args, **kwargs):
    """安全地运行异步函数，处理事件循环检测"""
    try:
        asyncio.get_running_loop()
        # 如果已在异步环境中，使用线程池执行
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, coro_func(*args, **kwargs))
            return future.result()
    except RuntimeError:
        # 没有运行中的事件循环，直接运行
        return asyncio.run(coro_func(*args, **kwargs))


class VectorKnowledgeManager:
    """向量化知识库管理器"""
    
    def __init__(self, 
                 knowledge_base_path: Optional[str] = None,
                 config: Optional[VectorIndexConfig] = None,
                 openai_api_key: Optional[str] = None):
        """初始化向量知识库管理器"""
        
        self.config = config or VectorIndexConfig()
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        
        if knowledge_base_path is None:
            self.knowledge_base_path = Path(__file__).parent / "knowledge_base"
        else:
            self.knowledge_base_path = Path(knowledge_base_path)
        
        # 智能位置管理器
        self.location_manager = SmartLocationManager()
        
        # FHIR患者上下文管理
        self.fhir_contexts: Dict[str, FHIRPatientContext] = {}
        self._fhir_enabled = os.getenv('USE_FHIR_FORMAT', 'true').lower() == 'true'
        
        # 尝试导入FHIR转换器
        self.fhir_converter = None
        if self._fhir_enabled:
            try:
                from fhir_data_converter import FHIRDataConverter
                self.fhir_converter = FHIRDataConverter()
                logger.info("✅ FHIR数据转换器已启用")
            except ImportError:
                logger.warning("⚠️ FHIR数据转换器未找到，将使用原始格式")
                self._fhir_enabled = False
        
        # 地理位置敏感度配置（基于Google Location Sensitivity专利）
        self.location_sensitivity_config = {
            # 高地理敏感度 - 5公里内（如餐厅、医院）
            'high_geo_sensitivity': {
                'keywords': ['餐厅', '咖啡厅', '药店', '医院', '诊所', '门诊', '急诊', '美食', '外卖', '体检'],
                'city_weight': 5.0,  # 同城市权重大幅提升
                'max_distance_km': 5,
                'description': '本地服务类查询，用户通常只关心附近5公里内的结果'
            },
            # 中等地理敏感度 - 50公里内（如购物、汽车）
            'medium_geo_sensitivity': {
                'keywords': ['购物', '商场', '银行', '汽车', '4S店', '维修', '培训', '学校', '保健品'],
                'city_weight': 2.5,
                'max_distance_km': 50,
                'description': '区域服务类查询，用户愿意在更大范围内寻找'
            },
            # 低地理敏感度 - 全国范围（如旅游、品牌、健康咨询）
            'low_geo_sensitivity': {
                'keywords': ['旅游', '景点', '酒店', '机票', '火车票', '攻略', '品牌', '营养', '健康', 
                           '血压', '失眠', '缺钙', '预防', '注意事项', '怎么判断', '如何', '什么是',
                           '免疫力', '骨质疏松', '心血管', '维生素', '补充'],
                'city_weight': 0.1,  # 大幅降低地理权重
                'max_distance_km': 1000,
                'description': '健康咨询和全国性查询，地理位置不重要'
            }
        }
        
        # 回答质量评估配置（基于Google RAG最佳实践）
        self.quality_metrics = {
            'response_groundedness': 0.0,  # 回答基于检索内容的程度
            'answer_relevance': 0.0,       # 回答与问题的相关度
            'context_precision': 0.0,      # 检索上下文的精确度
            'context_recall': 0.0,         # 检索上下文的召回率
            'verbosity_score': 0.0,        # 回答详细程度
            'instruction_following': 0.0   # 指令遵循程度
        }
        
        # 向量存储目录
        self.vector_store_path = self.knowledge_base_path / "vector_store"
        self.vector_store_path.mkdir(exist_ok=True)
        
        # 初始化嵌入模型
        self.embedding_model = None
        self._init_embedding_model()
        
        # 向量索引
        self.indexes = {}
        self.document_store = {}
        
        # 线程池
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        
        # 延迟加载向量索引（在首次使用时加载）
        self._indexes_loaded = False
        
        # 增强门诊匹配器（延迟初始化）
        self._enhanced_clinic_matcher = None
        
        # 性能优化：缓存
        self._embedding_cache = {}
        self._cache_lock = threading.Lock()
        
        # 性能优化：中文分词初始化
        if JIEBA_AVAILABLE:
            jieba.initialize()
            logger.info("✅ jieba中文分词初始化成功")
        
        # 性能优化：TF-IDF向量化器缓存
        self.tfidf_vectorizers = {}
        
        # 性能优化：部门特定索引
        self.department_indices = {}
        
        logger.info("VectorKnowledgeManager initialized with location sensitivity, quality assessment and performance optimizations")
    
    def _get_enhanced_clinic_matcher(self):
        """获取增强门诊匹配器（延迟初始化）"""
        if self._enhanced_clinic_matcher is None:
            try:
                from enhanced_clinic_matcher import ClinicMatcherAdapter
                self._enhanced_clinic_matcher = ClinicMatcherAdapter(self)
                logger.info("✅ 增强门诊匹配器初始化成功")
            except ImportError as e:
                logger.warning(f"增强门诊匹配器不可用: {e}")
                self._enhanced_clinic_matcher = None
        return self._enhanced_clinic_matcher
    
    def _init_embedding_model(self):
        """初始化嵌入模型"""
        try:
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                # 优先使用本地模型
                logger.info(f"正在初始化本地嵌入模型: {self.config.embedding_model}")
                self.embedding_model = SentenceTransformer(self.config.embedding_model)
                self.embedding_type = "sentence_transformers"
                logger.info(f"✅ 成功使用本地嵌入模型: {self.config.embedding_model}")
            elif self.openai_api_key or os.getenv("DEEPSEEK_API_KEY"):
                # 支持DeepSeek API
                api_key = self.openai_api_key or os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
                if OPENAI_AVAILABLE:
                    openai.api_key = api_key
                self.embedding_type = "openai"
                logger.info("✅ 使用OpenAI兼容API嵌入模型")
            else:
                logger.warning("没有找到API密钥，使用TF-IDF回退方案")
                self.embedding_type = "tfidf"
                self.embedding_model = None
        except Exception as e:
            logger.warning(f"嵌入模型初始化遇到问题: {e}，使用TF-IDF回退方案")
            self.embedding_model = None
            self.embedding_type = "tfidf"
    
    async def get_embeddings(self, texts: List[str]) -> np.ndarray:
        """获取文本嵌入向量 - 优化版本支持批处理和缓存"""
        # 如果文本数量较大，使用批处理版本
        if len(texts) > EMBEDDING_BATCH_SIZE:
            return await self._get_embeddings_batch(texts)
        
        if self.embedding_type == "sentence_transformers" and self.embedding_model is not None:
            # 创建一个局部引用来避免类型检查问题
            model = self.embedding_model
            if model is not None:
                return await asyncio.get_event_loop().run_in_executor(
                    self.executor, 
                    lambda: model.encode(texts, convert_to_numpy=True, batch_size=EMBEDDING_BATCH_SIZE)
                )
        elif self.embedding_type == "openai":
            return await self._get_openai_embeddings(texts)
        
        # 默认回退到TF-IDF向量化
        return await self._get_tfidf_embeddings(texts)
    
    async def _get_embeddings_batch(self, texts: List[str]) -> np.ndarray:
        """批量获取嵌入向量，带缓存优化"""
        embeddings = []
        uncached_texts = []
        uncached_indices = []
        
        # 检查缓存
        with self._cache_lock:
            for i, text in enumerate(texts):
                cache_key = hash(text)
                if cache_key in self._embedding_cache:
                    embeddings.append(self._embedding_cache[cache_key])
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(i)
        
        # 批量编码未缓存的文本
        if uncached_texts:
            logger.info(f"批量编码 {len(uncached_texts)} 个文本（总计 {len(texts)} 个）")
            
            # 分批处理
            new_embeddings = []
            for i in range(0, len(uncached_texts), EMBEDDING_BATCH_SIZE):
                batch = uncached_texts[i:i + EMBEDDING_BATCH_SIZE]
                batch_embeddings = await self.get_embeddings(batch)
                new_embeddings.extend(batch_embeddings)
            
            new_embeddings = np.array(new_embeddings)
            
            # 更新缓存
            with self._cache_lock:
                for text, embedding in zip(uncached_texts, new_embeddings):
                    cache_key = hash(text)
                    self._embedding_cache[cache_key] = embedding
            
            # 合并结果
            result = np.zeros((len(texts), self.config.embedding_dimension), dtype=np.float32)
            cached_idx = 0
            uncached_idx = 0
            
            for i in range(len(texts)):
                if i in uncached_indices:
                    result[i] = new_embeddings[uncached_idx]
                    uncached_idx += 1
                else:
                    result[i] = embeddings[cached_idx]
                    cached_idx += 1
            
            return result
        else:
            return np.array(embeddings, dtype=np.float32)
    
    async def _get_openai_embeddings(self, texts: List[str]) -> np.ndarray:
        """使用OpenAI获取嵌入向量"""
        try:
            if not OPENAI_AVAILABLE:
                raise ImportError("OpenAI module not available")
            
            # Use newer OpenAI API format
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)
            response = client.embeddings.create(
                model="text-embedding-ada-002",
                input=texts
            )
            embeddings = [item.embedding for item in response.data]
            return np.array(embeddings)
        except Exception as e:
            logger.error(f"OpenAI嵌入获取失败: {e}")
            return await self._get_tfidf_embeddings(texts)
    
    async def _get_tfidf_embeddings(self, texts: List[str]) -> np.ndarray:
        """回退的TF-IDF向量化"""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # 确保至少有一些文本
            if not texts:
                return np.array([]).reshape(0, 384)
            
            # 使用更保守的参数
            vectorizer = TfidfVectorizer(
                max_features=384, 
                stop_words=None,
                min_df=1,  # 确保所有词都被包含
                ngram_range=(1, 1)  # 只使用单词
            )
            
            # 处理空文本
            processed_texts = [text.strip() if text.strip() else "empty" for text in texts]
            
            embeddings = vectorizer.fit_transform(processed_texts).toarray()
            
            # 确保维度正确
            if embeddings.shape[1] < 384:
                # 如果维度不够，用零填充
                padding = np.zeros((embeddings.shape[0], 384 - embeddings.shape[1]))
                embeddings = np.hstack([embeddings, padding])
            elif embeddings.shape[1] > 384:
                # 如果维度太多，截断
                embeddings = embeddings[:, :384]
            
            return embeddings.astype('float32')
            
        except Exception as e:
            logger.error(f"TF-IDF向量化失败: {e}")
            # 最后的回退：标准化随机向量
            embeddings = np.random.rand(len(texts), 384).astype('float32')
            # 标准化
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms[norms == 0] = 1  # 避免除零
            return embeddings / norms

    def _load_indexes(self):
        """加载已有的向量索引"""
        try:
            for source in ["supplements", "clinics", "qa"]:
                index_file = self.vector_store_path / f"{source}_index.faiss"
                metadata_file = self.vector_store_path / f"{source}_metadata.pkl"
                
                if FAISS_AVAILABLE and index_file.exists():
                    self.indexes[source] = faiss.read_index(str(index_file))
                
                if metadata_file.exists():
                    with open(metadata_file, 'rb') as f:
                        self.document_store[source] = pickle.load(f)
                        
            logger.info("向量索引加载完成")
        except Exception as e:
            logger.error(f"索引加载失败: {e}")
    
    async def _build_all_indexes(self):
        """构建所有向量索引"""
        try:
            # 构建保健品索引
            await self._build_supplements_index()
            
            # 构建门诊索引
            await self._build_clinics_index()
            
            # 构建问答索引
            await self._build_qa_index()
            
            logger.info("所有向量索引构建完成")
        except Exception as e:
            logger.error(f"索引构建失败: {e}")
    
    async def _build_supplements_index(self):
        """构建保健品向量索引"""
        supplements_file = self.knowledge_base_path / "supplement_docs.csv"
        if not supplements_file.exists():
            logger.warning("保健品数据文件不存在")
            return
        
        try:
            df = pd.read_csv(supplements_file)
            
            # 创建文档块
            documents = []
            metadata = []
            
            for _, row in df.iterrows():
                # 组合多个字段创建富文本
                content_parts = []
                if pd.notna(row.get('商品名')):
                    content_parts.append(f"商品名: {row['商品名']}")
                if pd.notna(row.get('商品简介/功效')):
                    content_parts.append(f"功效: {row['商品简介/功效']}")
                if pd.notna(row.get('商品成分')):
                    content_parts.append(f"成分: {row['商品成分']}")
                if pd.notna(row.get('商品用量用法')):
                    content_parts.append(f"用法: {row['商品用量用法']}")
                if pd.notna(row.get('商品标签')):
                    content_parts.append(f"标签: {row['商品标签']}")
                
                content = " | ".join(content_parts)
                
                # 分块处理长文本
                chunks = self._split_text(content, self.config.chunk_size, self.config.chunk_overlap)
                
                for i, chunk in enumerate(chunks):
                    documents.append(chunk)
                    metadata.append({
                        "source": "supplements",
                        "product_name": row.get('商品名', ''),
                        "link": row.get('链接', ''),
                        "chunk_id": f"supplement_{len(metadata)}_{i}",
                        "original_data": row.to_dict()
                    })
            
            # 生成嵌入向量
            if documents:
                embeddings = await self.get_embeddings(documents)
                # 生成向量索引
                if FAISS_AVAILABLE:
                    dimension = embeddings.shape[1]
                    index = self._create_optimized_faiss_index(len(documents), dimension)
                    
                    # 如果是IVF索引，需要训练
                    if hasattr(index, 'is_trained') and not index.is_trained:
                        index.train(embeddings.astype('float32')) # type:ignore
                    
                    # 添加向量到索引
                    index.add(embeddings.astype('float32')) # type:ignore
                    
                    # 保存索引
                    faiss.write_index(index, str(self.vector_store_path / "supplements_index.faiss"))
                    self.indexes["supplements"] = index
                
                # 保存元数据
                self.document_store["supplements"] = {
                    "documents": documents,
                    "metadata": metadata,
                    "embeddings": embeddings if not FAISS_AVAILABLE else None
                }
                
                with open(self.vector_store_path / "supplements_metadata.pkl", 'wb') as f:
                    pickle.dump(self.document_store["supplements"], f)
                
                logger.info(f"保健品索引构建完成: {len(documents)}个文档块")
                
        except Exception as e:
            logger.error(f"保健品索引构建失败: {e}")
    
    async def _build_clinics_index(self):
        """构建门诊向量索引"""
        clinics_file = self.knowledge_base_path / "clinics.csv"
        if not clinics_file.exists():
            logger.warning("门诊数据文件不存在")
            return
        
        try:
            df = pd.read_csv(clinics_file)
            
            documents = []
            metadata = []
            
            for _, row in df.iterrows():
                content_parts = []
                
                # 门诊名称 - 增加权重，重复以提高匹配度
                if pd.notna(row.get('门诊名称')):
                    clinic_name = row['门诊名称']
                    content_parts.append(f"门诊: {clinic_name}")
                    content_parts.append(f"名称: {clinic_name}")  # 重复以增加权重
                    
                    # 如果是"体育西门诊部"，添加更多变体
                    if "体育西" in clinic_name:
                        content_parts.append("体育西路门诊 体育西门诊")
                
                # 核心科室 - 分解多科室
                if pd.notna(row.get('核心科室')):
                    dept_str = str(row['核心科室'])  # 确保是字符串
                    content_parts.append(f"科室: {dept_str}")
                    
                    # 分解科室列表
                    departments = [d.strip() for d in dept_str.replace('、', ',').split(',')]
                    for dept in departments:
                        if dept and dept != 'nan':
                            content_parts.append(f"专科: {dept}")
                
                # 服务内容
                if pd.notna(row.get('服务内容')):
                    services = row['服务内容']
                    content_parts.append(f"服务: {services}")
                    
                    # 提取关键服务词
                    if JIEBA_AVAILABLE:
                        service_keywords = jieba.analyse.extract_tags(services, topK=5, withWeight=False)
                        content_parts.extend(service_keywords)
                
                # 城市
                if pd.notna(row.get('城市')):
                    city = row['城市']
                    content_parts.append(f"城市: {city}")
                    content_parts.append(f"位于{city}")  # 增加位置表述
                
                # 地址 - 提取关键地标
                if pd.notna(row.get('门诊地址')):
                    address = row['门诊地址']
                    content_parts.append(f"地址: {address}")
                    
                    # 提取路名、大厦名等关键词
                    if "路" in address:
                        road = address.split('路')[0] + '路'
                        content_parts.append(f"位于{road}")
                    if "大厦" in address or "大楼" in address:
                        building = [part for part in address.split() if "大厦" in part or "大楼" in part]
                        if building:
                            content_parts.append(f"在{building[0]}")
                
                # 营业时间
                if pd.notna(row.get('营业时间')):
                    hours = row['营业时间']
                    if "周日" in hours or "周末" in hours:
                        content_parts.append("周末营业 周日开门")
                    if "24小时" in hours:
                        content_parts.append("24小时急诊")
                
                content = " | ".join(content_parts)
                documents.append(content)
                
                # 改进元数据结构
                dept_str = str(row.get('核心科室', '')) if pd.notna(row.get('核心科室')) else ''
                departments_list = []
                if dept_str and dept_str != 'nan':
                    departments_list = [d.strip() for d in dept_str.replace('、', ',').split(',') if d.strip() and d.strip() != 'nan']
                
                metadata.append({
                    "source": "clinics",
                    "name": row.get('门诊名称', ''),  # 添加name字段
                    "clinic_name": row.get('门诊名称', ''),
                    "department": dept_str if dept_str != 'nan' else '',
                    "departments": departments_list,  # 科室列表
                    "city": row.get('城市', ''),
                    "address": row.get('门诊地址', ''),
                    "services": row.get('服务内容', ''),
                    "hours": row.get('营业时间', ''),
                    "phone": row.get('门诊电话', ''),
                    "chunk_id": f"clinic_{len(metadata)}",
                    "original_data": row.to_dict()
                })
            
            if documents:
                embeddings = await self.get_embeddings(documents)
                
                if FAISS_AVAILABLE:
                    dimension = embeddings.shape[1]
                    index = self._create_optimized_faiss_index(len(documents), dimension)
                    
                    # 如果是IVF索引，需要训练
                    if hasattr(index, 'is_trained') and not index.is_trained:
                        index.train(embeddings.astype('float32')) # type:ignore
                    
                    index.add(embeddings.astype('float32')) # type:ignore
                    
                    faiss.write_index(index, str(self.vector_store_path / "clinics_index.faiss"))
                    self.indexes["clinics"] = index
                
                self.document_store["clinics"] = {
                    "documents": documents,
                    "metadata": metadata,
                    "embeddings": embeddings if not FAISS_AVAILABLE else None
                }
                
                with open(self.vector_store_path / "clinics_metadata.pkl", 'wb') as f:
                    pickle.dump(self.document_store["clinics"], f)
                
                logger.info(f"门诊索引构建完成: {len(documents)}个文档")
                
        except Exception as e:
            logger.error(f"门诊索引构建失败: {e}")
    
    async def _build_qa_index(self):
        """构建问答向量索引"""
        qa_file = self.knowledge_base_path / "nutrirec_qa.csv"
        if not qa_file.exists():
            logger.warning("问答数据文件不存在")
            return
        
        try:
            df = pd.read_csv(qa_file)
            
            documents = []
            metadata = []
            
            for _, row in df.iterrows():
                # 问题和答案组合
                question = row.get('问题', '')
                answer = row.get('回答', '')
                content = f"问题: {question} | 答案: {answer}"
                
                documents.append(content)
                metadata.append({
                    "source": "qa",
                    "question": question,
                    "answer": answer,
                    "chunk_id": f"qa_{len(metadata)}",
                    "original_data": row.to_dict()
                })
            
            if documents:
                embeddings = await self.get_embeddings(documents)
                
                if FAISS_AVAILABLE:
                    dimension = embeddings.shape[1]
                    index = self._create_optimized_faiss_index(len(documents), dimension)
                    
                    # 如果是IVF索引，需要训练
                    if hasattr(index, 'is_trained') and not index.is_trained:
                        index.train(embeddings.astype('float32')) # type:ignore
                    
                    index.add(embeddings.astype('float32')) # type:ignore
                    
                    faiss.write_index(index, str(self.vector_store_path / "qa_index.faiss"))
                    self.indexes["qa"] = index
                
                self.document_store["qa"] = {
                    "documents": documents,
                    "metadata": metadata,
                    "embeddings": embeddings if not FAISS_AVAILABLE else None
                }
                
                with open(self.vector_store_path / "qa_metadata.pkl", 'wb') as f:
                    pickle.dump(self.document_store["qa"], f)
                
                logger.info(f"问答索引构建完成: {len(documents)}个文档")
                
        except Exception as e:
            logger.error(f"问答索引构建失败: {e}")
    
    def _create_optimized_faiss_index(self, num_vectors: int, dimension: int) -> Any:
        """根据数据规模创建优化的FAISS索引"""
        if not FAISS_AVAILABLE:
            logger.warning("FAISS不可用，返回None")
            return None
            
        if num_vectors < IVF_THRESHOLD:
            # 小数据集使用Flat索引
            index = faiss.IndexFlatL2(dimension)
            logger.info(f"创建Flat索引，维度: {dimension}")
        else:
            # 大数据集使用IVF索引
            nlist = min(int(np.sqrt(num_vectors)), 100)
            quantizer = faiss.IndexFlatL2(dimension)
            index = faiss.IndexIVFFlat(quantizer, dimension, nlist)
            logger.info(f"创建IVF索引，维度: {dimension}, nlist: {nlist}")
        
        return index
    
    def _split_text(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """分割长文本为块"""
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            if end >= len(text):
                chunks.append(text[start:])
                break
            
            # 尝试在句号或换行处分割
            for sep in ['。', '\n', '，', ' ']:
                sep_pos = text.rfind(sep, start, end)
                if sep_pos > start:
                    end = sep_pos + 1
                    break
            
            chunks.append(text[start:end])
            start = end - overlap
        
        return chunks
    
    async def _ensure_indexes_loaded(self):
        """确保索引已加载"""
        if not self._indexes_loaded:
            try:
                await self._load_or_build_indexes_async()
                self._indexes_loaded = True
            except Exception as e:
                logger.error(f"索引加载失败: {e}")
    
    async def _load_or_build_indexes_async(self):
        """异步加载或构建向量索引"""
        try:
            # 检查是否已有缓存的索引
            index_files = {
                "supplements": self.vector_store_path / "supplements_index.faiss",
                "clinics": self.vector_store_path / "clinics_index.faiss",
                "qa": self.vector_store_path / "qa_index.faiss"
            }
            
            metadata_files = {
                "supplements": self.vector_store_path / "supplements_metadata.pkl",
                "clinics": self.vector_store_path / "clinics_metadata.pkl",
                "qa": self.vector_store_path / "qa_metadata.pkl"
            }
            
            need_rebuild = False
            for source in ["supplements", "clinics", "qa"]:
                if not (index_files[source].exists() and metadata_files[source].exists()):
                    need_rebuild = True
                    break
            
            if need_rebuild:
                logger.info("构建向量索引...")
                await self._build_all_indexes()
            else:
                logger.info("加载已有向量索引...")
                self._load_indexes()
                
        except Exception as e:
            logger.error(f"索引加载/构建失败: {e}")

    async def vector_search(self, 
                           query: str, 
                           sources: Optional[List[str]] = None,
                           max_results: Optional[int] = None) -> List[SearchResult]:
        """向量搜索"""
        if not query.strip():
            return []
        
        # 确保索引已加载
        await self._ensure_indexes_loaded()
        
        max_results = max_results or self.config.max_results
        sources = sources or ["supplements", "clinics", "qa"]
        
        all_results = []
        
        try:
            # 获取查询向量
            query_embedding = await self.get_embeddings([query])
            query_vector = query_embedding[0]
            
            for source in sources:
                if source not in self.indexes and source not in self.document_store:
                    continue
                
                if FAISS_AVAILABLE and source in self.indexes:
                    # 使用FAISS搜索
                    scores, indices = self.indexes[source].search(
                        query_vector.reshape(1, -1).astype('float32'), 
                        max_results
                    )
                    
                    # 改进的相似度计算 - 基于绝对距离阈值
                    for score, idx in zip(scores[0], indices[0]):
                        if idx >= 0 and score > 0:
                            # 使用分段函数，基于绝对距离值计算相似度
                            # 这样可以避免归一化导致的"所有查询都有高分结果"问题
                            
                            if score <= 3.0:  # 极高相似 (几乎完全匹配)
                                similarity = 0.95 + (3.0 - score) / 60.0  # 0.95-1.0
                            elif score <= 6.0:  # 很高相似
                                similarity = 0.85 + (6.0 - score) / 20.0  # 0.85-0.95
                            elif score <= 9.0:  # 高相似
                                similarity = 0.75 + (9.0 - score) / 30.0  # 0.75-0.85
                            elif score <= 12.0:  # 中等相似
                                similarity = 0.60 + (12.0 - score) / 20.0  # 0.60-0.75
                            elif score <= 18.0:  # 低相似
                                similarity = 0.40 + (18.0 - score) / 30.0  # 0.40-0.60
                            elif score <= 25.0:  # 很低相似
                                similarity = 0.20 + (25.0 - score) / 35.0  # 0.20-0.40
                            else:  # 基本无关
                                similarity = max(0.0, 0.20 - (score - 25.0) / 50.0)  # 0.0-0.20
                            
                            # 额外的质量控制：如果距离太大，强制降低分数
                            if score > 20.0:
                                similarity *= 0.5  # 距离过大的结果分数减半
                            
                            if similarity >= self.config.similarity_threshold:
                                    metadata = self.document_store[source]["metadata"][idx]
                                    content = self.document_store[source]["documents"][idx]
                                    
                                    all_results.append(SearchResult(
                                        content=content,
                                        metadata=metadata,
                                        score=similarity,
                                        source=source,
                                        chunk_id=metadata["chunk_id"]
                                    ))
                
                elif source in self.document_store:
                    # 回退到numpy计算
                    embeddings = self.document_store[source].get("embeddings")
                    if embeddings is not None:
                        similarities = np.dot(embeddings, query_vector) / (
                            np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vector)
                        )
                        
                        top_indices = np.argsort(similarities)[::-1][:max_results]
                        
                        for idx in top_indices:
                            if similarities[idx] >= self.config.similarity_threshold:
                                metadata = self.document_store[source]["metadata"][idx]
                                content = self.document_store[source]["documents"][idx]
                                
                                all_results.append(SearchResult(
                                    content=content,
                                    metadata=metadata,
                                    score=similarities[idx],
                                    source=source,
                                    chunk_id=metadata["chunk_id"]
                                ))
            
            # 按相似度排序并限制结果数量
            all_results.sort(key=lambda x: x.score, reverse=True)
            return all_results[:max_results]
            
        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []
    
    async def rag_search(self, 
                        query: str, 
                        sources: Optional[List[str]] = None,
                        context_window: int = 3) -> Dict[str, Any]:
        """RAG搜索 - 检索增强生成"""
        
        # 向量搜索获取相关文档
        search_results = await self.vector_search(query, sources)
        
        if not search_results:
            return {
                "query": query,
                "context": "",
                "sources": [],
                "confidence": 0.0
            }
        
        # 构建上下文
        context_parts = []
        source_info = []
        
        for result in search_results[:context_window]:
            context_parts.append(f"[来源: {result.source}] {result.content}")
            source_info.append({
                "source": result.source,
                "score": result.score,
                "chunk_id": result.chunk_id,
                "metadata": result.metadata
            })
        
        context = "\n\n".join(context_parts)
        avg_confidence = sum(r.score for r in search_results[:context_window]) / len(search_results[:context_window])
        
        return {
            "query": query,
            "context": context,
            "sources": source_info,
            "confidence": avg_confidence,
            "total_results": len(search_results)
        }
    
    async def hybrid_search(self, 
                           query: str,
                           sources: Optional[List[str]] = None,
                           vector_weight: float = 0.7,
                           session_id: Optional[str] = None) -> List[SearchResult]:
        """混合搜索 - 结合向量搜索和关键词搜索，支持FHIR上下文增强"""
        
        # FHIR查询增强
        if self._fhir_enabled and session_id:
            query = self._enhance_query_with_fhir_context(query, session_id)
        
        # 查询扩展
        source = sources[0] if sources and len(sources) == 1 else None
        expanded_query = self._expand_query(query, source)
        logger.info(f"查询扩展: '{query}' -> '{expanded_query}'")
        
        # 向量搜索
        vector_results = await self.vector_search(expanded_query, sources)
        
        # 关键词搜索
        keyword_results = await self._keyword_search(expanded_query, sources)
        
        # 结合结果
        combined_results = {}
        
        # 添加向量搜索结果
        for result in vector_results:
            key = result.chunk_id
            combined_results[key] = result
            combined_results[key].score *= vector_weight
        
        # 添加关键词搜索结果
        keyword_weight = 1.0 - vector_weight
        for result in keyword_results:
            key = result.chunk_id
            if key in combined_results:
                # 组合分数
                combined_results[key].score += result.score * keyword_weight
            else:
                result.score *= keyword_weight
                combined_results[key] = result
        
        # 排序并返回
        final_results = list(combined_results.values())
        final_results.sort(key=lambda x: x.score, reverse=True)
        
        return final_results[:self.config.max_results]

    async def _keyword_search(self, query: str, sources: Optional[List[str]] = None) -> List[SearchResult]:
        """智能关键词搜索 - 针对地名、专业术语等进行优化"""
        results = []
        sources = sources or ["supplements", "clinics", "qa"]
        
        query_lower = query.lower().strip()
        
        # 定义关键词匹配规则
        city_keywords = ['广州', '深圳', '北京', '上海', '重庆', '成都', '杭州', '南京', '武汉', '西安', '天津', '青岛', '大连', '厦门', '苏州', '东莞', '佛山', '汕头', '海口', '三亚', '番禺']
        dept_keywords = ['皮肤科', '儿科', '眼科', '内科', '外科', '妇科', '骨科', '神经科', '心内科', '消化科', '呼吸科', '泌尿科', '齿科', '口腔科', '耳鼻喉科', '康复科']
        
        for source in sources:
            if source not in self.document_store:
                continue
            
            documents = self.document_store[source]["documents"]
            metadata_list = self.document_store[source]["metadata"]
            
            for i, (doc, metadata) in enumerate(zip(documents, metadata_list)):
                doc_lower = doc.lower()
                original_data = metadata.get('original_data', {})
                
                # 多层次匹配策略
                match_score = 0.0
                match_reasons = []
                
                # 1. 精确匹配 (最高权重)
                if query_lower in doc_lower:
                    match_score += 1.0
                    match_reasons.append(f"精确匹配: {query}")
                
                # 2. 城市匹配 (最高权重 - 精确匹配优先)
                for city_keyword in city_keywords:
                    if city_keyword in query_lower:
                        city_field = str(original_data.get('城市', '')).lower()
                        if city_keyword in city_field:
                            match_score += 2.0  # 大幅提高城市精确匹配权重
                            match_reasons.append(f"城市精确匹配: {city_keyword}")
                            break
                        elif city_keyword in doc_lower:
                            match_score += 1.0
                            match_reasons.append(f"城市文档匹配: {city_keyword}")
                
                # 3. 科室匹配 (最高权重 - 精确匹配优先)
                for dept_keyword in dept_keywords:
                    if dept_keyword in query_lower:
                        dept_field = str(original_data.get('核心科室', '')).lower()
                        if dept_keyword in dept_field:
                            match_score += 2.0  # 大幅提高科室精确匹配权重
                            match_reasons.append(f"科室精确匹配: {dept_keyword}")
                            break
                        elif dept_keyword in doc_lower:
                            match_score += 1.0
                            match_reasons.append(f"科室文档匹配: {dept_keyword}")
                
                # 4. 门诊名称匹配 (中权重)
                clinic_name = str(original_data.get('门诊名称', '')).lower()
                if query_lower in clinic_name:
                    match_score += 0.8
                    match_reasons.append(f"门诊名称匹配: {query}")
                
                # 5. 服务内容匹配 (中权重)
                services = str(original_data.get('服务内容', '')).lower()
                if query_lower in services:
                    match_score += 0.6
                    match_reasons.append(f"服务内容匹配: {query}")
                
                # 6. 模糊匹配 (低权重)
                query_chars = set(query_lower)
                doc_chars = set(doc_lower)
                if len(query_chars) > 0:
                    char_overlap = len(query_chars.intersection(doc_chars)) / len(query_chars)
                    if char_overlap > 0.5:
                        match_score += char_overlap * 0.3
                        match_reasons.append(f"字符匹配: {char_overlap:.2f}")
                
                # 如果有匹配，创建搜索结果
                if match_score > 0.3:  # 设置最低匹配阈值
                    # 将关键词匹配分数映射到0-1区间
                    normalized_score = min(match_score, 1.0)
                    
                    results.append(SearchResult(
                        content=doc,
                        metadata=metadata,
                        score=normalized_score,
                        source=source,
                        chunk_id=metadata.get("chunk_id", f"{source}_{i}")
                    ))
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """获取知识库统计信息"""
        stats = {
            "embedding_model": self.config.embedding_model,
            "embedding_type": self.embedding_type,
            "faiss_available": FAISS_AVAILABLE,
            "indexes": {}
        }
        
        for source in ["supplements", "clinics", "qa"]:
            if source in self.document_store:
                doc_count = len(self.document_store[source]["documents"])
                stats["indexes"][source] = {
                    "document_count": doc_count,
                    "has_faiss_index": source in self.indexes,
                    "index_file_exists": (self.vector_store_path / f"{source}_index.faiss").exists()
                }
        
        return stats
    
    async def build_department_specific_indices(self, source: str = 'clinics'):
        """构建部门特定的子索引以提高搜索精度"""
        if source != 'clinics':
            logger.info(f"部门索引仅支持clinics来源，跳过 {source}")
            return
        
        # 确保主索引已加载
        await self._ensure_indexes_loaded()
        
        if 'clinics' not in self.document_store:
            logger.warning("没有clinics数据可用于构建部门索引")
            return
        
        logger.info("开始构建部门特定索引...")
        start_time = time.time()
        
        # 按部门分组文档
        department_docs = {}
        department_embeddings = {}
        
        # 检查是否有embeddings
        has_embeddings = ('embeddings' in self.document_store.get('clinics', {}) and 
                         self.document_store['clinics']['embeddings'] is not None)
        
        for i, metadata in enumerate(self.document_store['clinics']['metadata']):
            # 使用改进后的departments列表
            departments = metadata.get('departments', [])
            if not departments:
                # 回退到旧的department字段
                dept_str = metadata.get('department', '')
                if dept_str:
                    departments = [d.strip() for d in dept_str.replace('、', ',').split(',') if d.strip()]
            
            # 为每个科室添加文档
            for dept in departments:
                if dept and dept not in ['', 'N/A', 'nan']:
                    if dept not in department_docs:
                        department_docs[dept] = []
                        department_embeddings[dept] = []
                    
                    doc_info = {
                        'document': self.document_store['clinics']['documents'][i],
                        'metadata': metadata
                    }
                    
                    if has_embeddings:
                        doc_info['embedding'] = self.document_store['clinics']['embeddings'][i]
                        department_embeddings[dept].append(self.document_store['clinics']['embeddings'][i])
                    
                    department_docs[dept].append(doc_info)
        
        # 为每个部门创建索引
        for dept, docs in department_docs.items():
            if len(docs) < 2:  # 降低最小文档数要求
                continue
                
            logger.info(f"构建部门索引: {dept} ({len(docs)} 个文档)")
            
            # 如果没有预先计算的embeddings，需要生成
            if not has_embeddings or not department_embeddings[dept]:
                texts = [d['document'] for d in docs]
                embeddings = await self.get_embeddings(texts)
            else:
                embeddings = np.array(department_embeddings[dept], dtype=np.float32)
            
            if FAISS_AVAILABLE:
                dimension = embeddings.shape[1]
                dept_index = self._create_optimized_faiss_index(len(embeddings), dimension)
                
                if hasattr(dept_index, 'is_trained') and not dept_index.is_trained:
                    dept_index.train(embeddings)
                
                dept_index.add(embeddings)
                
                self.department_indices[f"clinics_{dept}"] = {
                    'index': dept_index,
                    'documents': [d['document'] for d in docs],
                    'metadata': [d['metadata'] for d in docs],
                    'embeddings': embeddings
                }
        
        elapsed_time = time.time() - start_time
        logger.info(f"✅ 构建了 {len(self.department_indices)} 个部门索引，耗时: {elapsed_time:.2f}秒")
    
    async def search_with_department_index(self, 
                                         query: str,
                                         department: str,
                                         top_k: int = 5) -> List[SearchResult]:
        """使用部门特定索引搜索"""
        dept_key = f"clinics_{department}"
        
        if dept_key not in self.department_indices:
            logger.info(f"部门 {department} 没有专用索引，使用通用搜索")
            results = await self.hybrid_search(
                query=query,
                sources=['clinics']
            )
            return results[:top_k]
        
        # 查询扩展
        expanded_query = self._expand_query(query, 'clinics')
        
        # 获取查询嵌入
        query_embeddings = await self.get_embeddings([expanded_query])
        query_vector = query_embeddings[0]
        
        # 在部门索引中搜索
        dept_data = self.department_indices[dept_key]
        
        if FAISS_AVAILABLE and 'index' in dept_data:
            distances, indices = dept_data['index'].search(
                query_vector.reshape(1, -1).astype('float32'), 
                min(top_k, len(dept_data['documents']))
            )
            
            results = []
            for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < len(dept_data['documents']):
                    result = SearchResult(
                        content=dept_data['documents'][idx],
                        metadata=dept_data['metadata'][idx],
                        score=float(1 / (1 + dist)),
                        source='clinics',
                        chunk_id=dept_data['metadata'][idx].get('chunk_id', str(idx))
                    )
                    results.append(result)
        else:
            # 回退到numpy计算
            embeddings = dept_data['embeddings']
            similarities = np.dot(embeddings, query_vector) / (
                np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vector)
            )
            
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for idx in top_indices:
                if similarities[idx] >= self.config.similarity_threshold:
                    result = SearchResult(
                        content=dept_data['documents'][idx],
                        metadata=dept_data['metadata'][idx],
                        score=float(similarities[idx]),
                        source='clinics',
                        chunk_id=dept_data['metadata'][idx].get('chunk_id', str(idx))
                    )
                    results.append(result)
        
        return results
    
    async def rebuild_index(self, source: Optional[str] = None):
        """重建指定或所有索引"""
        if source:
            if source == "supplements":
                await self._build_supplements_index()
            elif source == "clinics":
                await self._build_clinics_index()
            elif source == "qa":
                await self._build_qa_index()
        else:
            await self._build_all_indexes()

    def determine_location_sensitivity(self, query: str) -> Dict[str, Any]:
        """
        确定查询的地理位置敏感度
        基于Google Location Sensitivity专利的实现
        """
        query_lower = query.lower()
        
        # 检查每个敏感度级别
        for sensitivity_level, config in self.location_sensitivity_config.items():
            for keyword in config['keywords']:
                if keyword in query_lower:
                    return {
                        'level': sensitivity_level,
                        'city_weight': config['city_weight'],
                        'max_distance_km': config['max_distance_km'],
                        'description': config['description'],
                        'matched_keyword': keyword
                    }
        
        # 默认中等敏感度
        return {
            'level': 'medium_geo_sensitivity',
            'city_weight': 2.5,
            'max_distance_km': 50,
            'description': '默认中等地理敏感度',
            'matched_keyword': None
        }

    def _chinese_tokenize(self, text: str) -> List[str]:
        """中文分词优化"""
        if not JIEBA_AVAILABLE:
            # 简单的字符分割
            return list(filter(lambda x: len(x) > 1, text.split()))
        
        # 使用jieba进行分词
        words = jieba.cut(text, cut_all=False)
        # 过滤停用词和短词
        return [w for w in words if len(w) > 1]
    
    def _expand_query(self, query: str, source: Optional[str] = None) -> str:
        """查询扩展，添加相关医学术语"""
        expanded_terms = []
        
        if JIEBA_AVAILABLE:
            # 提取关键词
            keywords = jieba.analyse.extract_tags(query, topK=5, withWeight=False)
            expanded_terms.extend(keywords)
        
        # 医学术语映射
        medical_terms = {
            '糖尿病': ['血糖', '胰岛素', '糖化血红蛋白', '降糖'],
            '高血压': ['血压', '降压', '心血管', '动脉'],
            '心脏': ['心血管', '心脏病', '冠心病', '心肌'],
            '肿瘤': ['癌症', '肿瘤', '化疗', '抗癌'],
            '骨质疏松': ['骨密度', '钙', '维生素D', '骨折'],
            '失眠': ['睡眠', '入睡困难', '睡眠质量', '褪黑素'],
            '免疫': ['免疫力', '抵抗力', '免疫系统', '维生素C'],
            '消化': ['肠胃', '消化不良', '益生菌', '肠道']
        }
        
        for term, related in medical_terms.items():
            if term in query:
                expanded_terms.extend(related)
        
        # 根据来源添加特定术语
        if source == 'clinics':
            clinic_terms = ['门诊', '医院', '诊所', '科室', '专家', '挂号']
            expanded_terms.extend([t for t in clinic_terms if t not in query])
        elif source == 'supplements':
            supplement_terms = ['保健品', '营养品', '补充剂', '胶囊', '片剂']
            expanded_terms.extend([t for t in supplement_terms if t not in query])
        
        # 组合原始查询和扩展词
        expanded_query = f"{query} {' '.join(set(expanded_terms))}"
        return expanded_query
    
    def extract_geographic_entities(self, query: str) -> Dict[str, List[str]]:
        """从查询中提取地理实体"""
        # 中国主要城市（可扩展）
        cities = ['北京', '上海', '广州', '深圳', '成都', '杭州', '武汉', '西安', 
                 '南京', '天津', '重庆', '苏州', '长沙', '郑州', '青岛', '大连',
                 '宁波', '厦门', '福州', '济南', '合肥', '昆明', '海口', '东莞',
                 '佛山', '汕头', '珠海', '中山', '惠州', '江门', '湛江', '茂名']
        
        # 行政区划
        districts = ['朝阳区', '海淀区', '西城区', '东城区', '丰台区', '石景山区',
                    '浦东新区', '黄浦区', '徐汇区', '长宁区', '静安区', '普陀区',
                    '天河区', '越秀区', '荔湾区', '海珠区', '白云区', '番禺区']
        
        found_entities = {
            'cities': [city for city in cities if city in query],
            'districts': [district for district in districts if district in query]
        }
        
        return found_entities

    def calculate_location_prominence_score(self, query: str, document_metadata: Dict) -> float:
        """
        计算位置显著性分数
        基于Google Location Prominence专利实现
        """
        score = 0.0
        geo_sensitivity = self.determine_location_sensitivity(query)
        city_weight = geo_sensitivity['city_weight']
        
        # 提取查询中的地理实体
        query_geo = self.extract_geographic_entities(query)
        
        # 文档中的城市信息
        doc_city = str(document_metadata.get('original_data', {}).get('城市', '')).lower()
        doc_district = str(document_metadata.get('original_data', {}).get('区域', '')).lower()
        
        # 城市精确匹配（最高权重）- 大幅提升同城市权重
        for query_city in query_geo['cities']:
            if query_city.lower() in doc_city:
                score += city_weight * 5.0  # 大幅提升精确城市匹配权重
                logger.debug(f"城市精确匹配: {query_city} -> +{city_weight * 5.0}")
                return score  # 找到精确匹配后立即返回，确保同城市优先
        
        # 区域匹配
        for query_district in query_geo['districts']:
            if query_district.lower() in doc_district:
                score += city_weight * 3.0  # 提升区域匹配权重
                logger.debug(f"区域匹配: {query_district} -> +{city_weight * 3.0}")
                break
        
        # 如果有地理条件但没匹配到，给予惩罚分
        if query_geo['cities'] or query_geo['districts']:
            score -= city_weight * 1.0  # 地理不匹配的惩罚
        elif geo_sensitivity['level'] == 'high_geo_sensitivity':
            score += 0.5  # 高敏感度查询的基础分
        
        return score

    async def smart_search_with_adaptive_location(self, 
                                                 query: str, 
                                                 sources: Optional[List[str]] = None,
                                                 max_results: int = 5,
                                                 user_city: Optional[str] = None,
                                                 conversation_history: Optional[List[Dict]] = None,
                                                 use_enhanced_clinic_matching: bool = True,
                                                 session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        智能搜索 - 自适应处理地理位置信息
        支持多种位置获取方式，无位置信息时也能正常工作
        支持增强门诊匹配、multi-agent上下文集成和FHIR患者上下文
        """
        
        # FHIR查询增强
        if self._fhir_enabled and session_id:
            original_query = query
            query = self._enhance_query_with_fhir_context(query, session_id)
            if query != original_query:
                logger.info(f"🔍 FHIR增强查询: '{original_query}' -> '{query}'")
        # 1. 检查是否为门诊相关查询且启用增强匹配
        is_clinic_query = sources is None or "clinics" in (sources or [])
        clinic_keywords = ["门诊", "医院", "诊所", "科室", "医生", "就医", "看病", "治疗"]
        has_clinic_intent = any(keyword in query for keyword in clinic_keywords)
        
        enhanced_matcher = self._get_enhanced_clinic_matcher()
        if (use_enhanced_clinic_matching and 
            is_clinic_query and 
            has_clinic_intent and 
            enhanced_matcher is not None):
            
            logger.info("🏥 使用增强门诊匹配系统")
            try:
                enhanced_results = await enhanced_matcher.enhanced_clinic_search_with_context(
                    query=query,
                    user_city=user_city,
                    conversation_history=conversation_history,
                    max_results=max_results
                )
                
                # 添加位置信息和建议
                if user_city:
                    self.location_manager.set_user_location(user_city, "manual", 1.0)
                
                location_info = self.location_manager.get_effective_location(query)
                geo_sensitivity = self.determine_location_sensitivity(query)
                
                enhanced_results.update({
                    'location_info': location_info,
                    'geo_sensitivity': geo_sensitivity,
                    'search_metadata': {
                        **enhanced_results.get('search_metadata', {}),
                        'enhanced_clinic_matching': True,
                        'multi_agent_context': conversation_history is not None
                    }
                })
                
                return enhanced_results
                
            except Exception as e:
                logger.warning(f"增强门诊匹配失败，回退到标准搜索: {e}")
        
        # 2. 标准搜索流程
        # 获取有效的位置信息
        if user_city:
            # 如果明确提供了用户城市，设置为当前位置
            self.location_manager.set_user_location(user_city, "manual", 1.0)
        
        location_info = self.location_manager.get_effective_location(query)
        
        # 执行搜索
        search_results = await self.enhanced_hybrid_search_with_location(
            query, sources, max_results
        )
        
        # 3. 如果是地理敏感查询但没有位置信息，提供位置设置建议
        geo_sensitivity = self.determine_location_sensitivity(query)
        location_suggestion = None
        
        if (geo_sensitivity['level'] == 'high_geo_sensitivity' and 
            location_info['confidence'] < 0.5):
            # 获取可用城市列表
            available_cities = self._get_available_cities_from_data()
            location_suggestion = self.location_manager.suggest_location_setup(available_cities)
        
        return {
            'results': search_results,
            'location_info': location_info,
            'geo_sensitivity': geo_sensitivity,
            'location_suggestion': location_suggestion,
            'search_metadata': {
                'query': query,
                'total_results': len(search_results),
                'search_strategy': 'adaptive_location'
            }
        }
    
    def _get_available_cities_from_data(self) -> List[str]:
        """从数据中获取可用城市列表"""
        try:
            clinics_file = self.knowledge_base_path / "clinics.csv"
            if clinics_file.exists():
                df = pd.read_csv(clinics_file)
                return sorted(df['城市'].dropna().unique().tolist())
        except Exception as e:
            logger.error(f"获取可用城市列表失败: {e}")
        
        # 返回默认城市列表
        return ['广州', '深圳', '佛山', '东莞', '珠海', '汕头', '成都', '重庆', '海口']
    
    def update_patient_context(self, session_id: str, user_profile: Dict[str, Any]) -> Optional[FHIRPatientContext]:
        """更新患者的FHIR上下文"""
        if not self._fhir_enabled or not self.fhir_converter:
            return None
        
        try:
            # 转换为FHIR格式
            fhir_patient = self.fhir_converter.convert_to_fhir_patient(user_profile)
            
            # 创建或更新FHIR上下文
            context = FHIRPatientContext(
                patient_id=fhir_patient.get('id'),
                fhir_patient_data=fhir_patient,
                last_synced=pd.Timestamp.now().isoformat(),
                sync_status="synced"
            )
            
            self.fhir_contexts[session_id] = context
            logger.info(f"✅ 更新FHIR患者上下文: {session_id}")
            
            # 从FHIR数据中提取位置信息
            if fhir_patient.get('address') and len(fhir_patient['address']) > 0:
                address = fhir_patient['address'][0]
                if address.get('city'):
                    self.location_manager.set_user_location(
                        address['city'], 
                        source="fhir_patient", 
                        confidence=0.95
                    )
            
            return context
            
        except Exception as e:
            logger.error(f"更新FHIR患者上下文失败: {e}")
            return None
    
    def _enhance_query_with_fhir_context(self, query: str, session_id: Optional[str]) -> str:
        """使用FHIR上下文增强查询"""
        if not session_id or session_id not in self.fhir_contexts:
            return query
        
        context = self.fhir_contexts[session_id]
        if not context.fhir_patient_data:
            return query
        
        # 从FHIR数据中提取相关信息
        enhancements = []
        patient_data = context.fhir_patient_data
        
        # 添加性别信息（如果查询涉及性别相关）
        if any(keyword in query for keyword in ['男', '女', '性别', '妇科', '男科']):
            gender = patient_data.get('gender')
            if gender:
                gender_cn = {'male': '男性', 'female': '女性'}.get(gender, gender)
                enhancements.append(f"患者性别:{gender_cn}")
        
        # 添加年龄信息（如果查询涉及年龄相关）
        if any(keyword in query for keyword in ['老年', '儿童', '年龄', '儿科', '老人']):
            birth_date = patient_data.get('birthDate')
            if birth_date:
                birth_year = int(birth_date.split('-')[0])
                age = pd.Timestamp.now().year - birth_year
                if age < 18:
                    enhancements.append("儿童患者")
                elif age > 65:
                    enhancements.append("老年患者")
        
        # 添加已知疾病信息（从扩展字段）
        for extension in patient_data.get('extension', []):
            if extension.get('url') == "http://nutrirec.example.com/fhir/StructureDefinition/medical-history":
                try:
                    medical_history = json.loads(extension['valueString'])
                    if isinstance(medical_history, list) and medical_history:
                        enhancements.append(f"既往史:{','.join(medical_history[:2])}")
                except:
                    pass
        
        # 如果有增强信息，添加到查询
        if enhancements:
            enhanced_query = f"{query} ({' '.join(enhancements)})"
            logger.info(f"🔍 FHIR增强查询: {enhanced_query}")
            return enhanced_query
        
        return query

    def set_fhir_patient_context(self, session_id: str, patient_data: Dict[str, Any]) -> None:
        """设置会话的FHIR患者上下文"""
        if not self._fhir_enabled:
            return
        
        if session_id not in self.fhir_contexts:
            self.fhir_contexts[session_id] = FHIRPatientContext()
        
        self.fhir_contexts[session_id].patient_id = patient_data.get('id')
        self.fhir_contexts[session_id].fhir_patient_data = patient_data
        
        logger.info(f"✅ 设置FHIR患者上下文 - 会话: {session_id}, 患者ID: {patient_data.get('id')}")

    def get_fhir_patient_context(self, session_id: str) -> Optional[FHIRPatientContext]:
        """获取会话的FHIR患者上下文"""
        return self.fhir_contexts.get(session_id)

    def clear_fhir_patient_context(self, session_id: str) -> None:
        """清除会话的FHIR患者上下文"""
        if session_id in self.fhir_contexts:
            del self.fhir_contexts[session_id]
            logger.info(f"🗑️ 清除FHIR患者上下文 - 会话: {session_id}")

    async def enhanced_hybrid_search_with_location(self, 
                                                  query: str, 
                                                  sources: Optional[List[str]] = None,
                                                  max_results: int = 5) -> List[SearchResult]:
        """
        增强的混合搜索 - 结合地理位置敏感度
        """
        if not query.strip():
            return []
        
        await self._ensure_indexes_loaded()
        
        sources = sources or ["supplements", "clinics", "qa"]
        all_results = []
        
        try:
            # 获取查询向量
            query_embedding = await self.get_embeddings([query])
            query_vector = query_embedding[0]
            
            # 确定地理位置敏感度
            geo_sensitivity = self.determine_location_sensitivity(query)
            logger.info(f"Query geo sensitivity: {geo_sensitivity['level']} (weight: {geo_sensitivity['city_weight']})")
            
            for source in sources:
                if source not in self.indexes and source not in self.document_store:
                    continue
                
                source_results = []
                
                if FAISS_AVAILABLE and source in self.indexes:
                    # 使用FAISS搜索
                    scores, indices = self.indexes[source].search(
                        query_vector.reshape(1, -1).astype('float32'), 
                        max_results * 2  # 获取更多候选，然后基于位置重排序
                    )
                    
                    for score, idx in zip(scores[0], indices[0]):
                        if idx >= 0 and score > 0:
                            # 基础向量相似度
                            if score <= 3.0:
                                base_similarity = 0.95 + (3.0 - score) / 60.0
                            elif score <= 6.0:
                                base_similarity = 0.85 + (6.0 - score) / 20.0
                            elif score <= 9.0:
                                base_similarity = 0.75 + (9.0 - score) / 30.0
                            elif score <= 12.0:
                                base_similarity = 0.60 + (12.0 - score) / 20.0
                            elif score <= 18.0:
                                base_similarity = 0.40 + (18.0 - score) / 30.0
                            elif score <= 25.0:
                                base_similarity = 0.20 + (25.0 - score) / 35.0
                            else:
                                base_similarity = max(0.0, 0.20 - (score - 25.0) / 50.0)
                            
                            if score > 20.0:
                                base_similarity *= 0.5
                            
                            if base_similarity >= self.config.similarity_threshold:
                                metadata = self.document_store[source]["metadata"][idx]
                                content = self.document_store[source]["documents"][idx]
                                
                                # 计算位置显著性分数
                                location_score = self.calculate_location_prominence_score(query, metadata)
                                
                                # 组合最终分数
                                final_score = base_similarity + location_score
                                
                                source_results.append(SearchResult(
                                    content=content,
                                    metadata={
                                        **metadata,
                                        'base_similarity': base_similarity,
                                        'location_score': location_score,
                                        'geo_sensitivity': geo_sensitivity['level']
                                    },
                                    score=final_score,
                                    source=source,
                                    chunk_id=metadata["chunk_id"]
                                ))
                
                # 按最终分数排序并选择top结果
                source_results.sort(key=lambda x: x.score, reverse=True)
                all_results.extend(source_results[:max_results])
            
            # 最终排序
            all_results.sort(key=lambda x: x.score, reverse=True)
            return all_results[:max_results]
            
        except Exception as e:
            logger.error(f"Enhanced hybrid search failed: {e}")
            return []

    async def evaluate_response_quality(self, 
                                       query: str, 
                                       response: str, 
                                       retrieved_context: List[str]) -> Dict[str, float]:
        """
        评估回答质量
        基于Google RAG评估最佳实践
        """
        quality_scores = {}
        
        try:
            # 1. Response Groundedness - 回答基于检索内容的程度
            groundedness = self._calculate_groundedness(response, retrieved_context)
            quality_scores['response_groundedness'] = groundedness
            
            # 2. Answer Relevance - 回答与问题的相关度
            relevance = await self._calculate_answer_relevance(query, response)
            quality_scores['answer_relevance'] = relevance
            
            # 3. Context Precision - 检索上下文的精确度
            precision = self._calculate_context_precision(query, retrieved_context)
            quality_scores['context_precision'] = precision
            
            # 4. Context Recall - 检索上下文的召回率（估算）
            recall = self._estimate_context_recall(query, retrieved_context)
            quality_scores['context_recall'] = recall
            
            # 5. Verbosity Score - 回答详细程度
            verbosity = self._calculate_verbosity_score(response)
            quality_scores['verbosity_score'] = verbosity
            
            # 6. Instruction Following - 指令遵循程度
            instruction_following = self._calculate_instruction_following(query, response)
            quality_scores['instruction_following'] = instruction_following
            
            # 计算综合质量分数
            quality_scores['overall_quality'] = (
                groundedness * 0.25 +
                relevance * 0.25 +
                precision * 0.2 +
                recall * 0.15 +
                verbosity * 0.1 +
                instruction_following * 0.05
            )
            
            return quality_scores
            
        except Exception as e:
            logger.error(f"Response quality evaluation failed: {e}")
            return {metric: 0.0 for metric in ['response_groundedness', 'answer_relevance', 
                                             'context_precision', 'context_recall', 
                                             'verbosity_score', 'instruction_following', 'overall_quality']}

    def _calculate_groundedness(self, response: str, context: List[str]) -> float:
        """计算回答基于上下文的程度"""
        if not response or not context:
            return 0.0
        
        # 使用更智能的分词和匹配策略
        import re
        
        # 提取有意义的词汇（去除停用词和标点）
        def extract_meaningful_words(text):
            # 中文分词和英文分词
            words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+\d*', text.lower())
            # 过滤掉常见停用词
            stop_words = {'的', '是', '在', '有', '和', '与', '或', '但', '而', '了', '着', '过', '将', '会', '能', '可以', '建议', '推荐', 'the', 'is', 'and', 'or', 'but', 'with', 'for', 'to', 'of', 'in', 'on', 'at'}
            return set([w for w in words if len(w) > 1 and w not in stop_words])
        
        response_words = extract_meaningful_words(response)
        context_words = set()
        for ctx in context:
            context_words.update(extract_meaningful_words(ctx))
        
        if not response_words:
            return 0.0
        
        # 计算回答中有多少重要词来自上下文
        grounded_words = response_words.intersection(context_words)
        groundedness = len(grounded_words) / len(response_words)
        
        # 如果有专业术语匹配，给予额外加分
        professional_terms = {'门诊', '医院', '科室', '保健品', '维生素', '钙镁', '营养', '健康', '治疗', '诊断'}
        professional_matches = response_words.intersection(context_words).intersection(professional_terms)
        if professional_matches:
            groundedness += len(professional_matches) * 0.1  # 专业术语匹配加分
        
        return min(groundedness, 1.0)

    async def _calculate_answer_relevance(self, query: str, response: str) -> float:
        """计算回答与问题的相关度"""
        try:
            # 使用向量相似度计算
            if self.embedding_model:
                embeddings = await self.get_embeddings([query, response])
                query_vec, response_vec = embeddings[0], embeddings[1]
                
                # 计算余弦相似度
                similarity = np.dot(query_vec, response_vec) / (
                    np.linalg.norm(query_vec) * np.linalg.norm(response_vec)
                )
                return float(similarity)
            else:
                # 简单的词汇重叠度
                query_words = set(query.lower().split())
                response_words = set(response.lower().split())
                
                if not query_words:
                    return 0.0
                
                overlap = len(query_words.intersection(response_words))
                return overlap / len(query_words)
                
        except Exception as e:
            logger.error(f"Answer relevance calculation failed: {e}")
            return 0.0

    def _calculate_context_precision(self, query: str, context: List[str]) -> float:
        """计算上下文精确度"""
        if not context:
            return 0.0
        
        query_words = set(query.lower().split())
        relevant_contexts = 0
        
        for ctx in context:
            ctx_words = set(ctx.lower().split())
            overlap = len(query_words.intersection(ctx_words))
            
            # 如果上下文与查询有足够重叠，认为是相关的
            if overlap > 0 and overlap / len(query_words) > 0.1:
                relevant_contexts += 1
        
        return relevant_contexts / len(context)

    def _estimate_context_recall(self, query: str, context: List[str]) -> float:
        """估算上下文召回率"""
        # 这是一个简化的估算，实际应用中可能需要更复杂的方法
        if not context:
            return 0.0
        
        # 基于上下文数量和质量的启发式估算
        context_quality = self._calculate_context_precision(query, context)
        context_quantity_factor = min(len(context) / 3.0, 1.0)  # 假设3个上下文是理想的
        
        return (context_quality + context_quantity_factor) / 2.0

    def _calculate_verbosity_score(self, response: str) -> float:
        """计算回答详细程度分数"""
        if not response:
            return 0.0
        
        word_count = len(response.split())
        
        # 理想的回答长度在50-200词之间
        if 50 <= word_count <= 200:
            return 1.0
        elif word_count < 50:
            return word_count / 50.0  # 太短
        else:
            return max(0.3, 1.0 - (word_count - 200) / 300.0)  # 太长

    def _calculate_instruction_following(self, query: str, response: str) -> float:
        """计算指令遵循程度"""
        if not query or not response:
            return 0.0
        
        # 检查是否直接回答了问题
        score = 0.0
        
        # 如果查询是问句，检查回答是否包含答案
        if '?' in query or '什么' in query or '如何' in query or '怎么' in query:
            if len(response) > 10:  # 有实质性回答
                score += 0.5
            if '建议' in response or '推荐' in response or '可以' in response:
                score += 0.3
        
        # 检查回答是否结构化
        if '。' in response or '，' in response:  # 有标点符号，说明结构化
            score += 0.2
        
        return min(score, 1.0)


# 全局向量知识库管理器实例
_global_vector_knowledge_manager = None

def get_vector_knowledge_manager() -> VectorKnowledgeManager:
    """获取全局向量知识库管理器实例"""
    global _global_vector_knowledge_manager
    
    if _global_vector_knowledge_manager is None:
        _global_vector_knowledge_manager = VectorKnowledgeManager()
    
    return _global_vector_knowledge_manager

# 兼容旧接口的便捷函数
def get_knowledge_manager():
    """获取全局知识库管理器实例 - 直接返回VectorKnowledgeManager"""
    return get_vector_knowledge_manager()

def search_clinics(department: Optional[str] = None, city: Optional[str] = None) -> List[Dict[str, Any]]:
    """搜索门诊信息 - 优化版本，优先精确匹配"""
    import asyncio
    
    vkm = get_vector_knowledge_manager()
    
    # 优化查询构建 - 使用更自然的语言
    query_parts = []
    if city:
        query_parts.append(f"{city}市门诊")  # 更自然的表达
    if department:
        query_parts.append(f"{department}门诊")  # 更自然的表达
    
    if not query_parts:
        query = "优质门诊推荐"
    else:
        query = " ".join(query_parts)
    
    try:
        # 使用混合搜索提高召回率
        try:
            asyncio.get_running_loop()
            # 如果已在异步环境中，使用线程池执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # 优先使用混合搜索 - 为精确匹配降低向量权重
                vector_weight = 0.3 if (department or city) else 0.6  # 有具体条件时更依赖关键词搜索
                future = executor.submit(asyncio.run, vkm.hybrid_search(query, sources=["clinics"], vector_weight=vector_weight))
                hybrid_results = future.result()
                
                # 如果混合搜索结果不足，再用RAG搜索
                if len(hybrid_results) < 3:
                    future_rag = executor.submit(asyncio.run, vkm.rag_search(query, sources=["clinics"]))
                    rag_result = future_rag.result()
                else:
                    # 从混合搜索结果构建RAG格式
                    rag_result = {
                        "query": query,
                        "context": "\n\n".join([f"[来源: {r.source}] {r.content}" for r in hybrid_results[:3]]),
                        "sources": [{"source": r.source, "score": r.score, "chunk_id": r.chunk_id, "metadata": r.metadata} for r in hybrid_results],
                        "confidence": sum(r.score for r in hybrid_results[:3]) / min(3, len(hybrid_results)),
                        "total_results": len(hybrid_results)
                    }
        except RuntimeError:
            # 没有运行中的事件循环，直接运行
            vector_weight = 0.3 if (department or city) else 0.6  # 有具体条件时更依赖关键词搜索
            hybrid_results = asyncio.run(vkm.hybrid_search(query, sources=["clinics"], vector_weight=vector_weight))
            
            if len(hybrid_results) < 3:
                rag_result = asyncio.run(vkm.rag_search(query, sources=["clinics"]))
            else:
                rag_result = {
                    "query": query,
                    "context": "\n\n".join([f"[来源: {r.source}] {r.content}" for r in hybrid_results[:3]]),
                    "sources": [{"source": r.source, "score": r.score, "chunk_id": r.chunk_id, "metadata": r.metadata} for r in hybrid_results],
                    "confidence": sum(r.score for r in hybrid_results[:3]) / min(3, len(hybrid_results)),
                    "total_results": len(hybrid_results)
                }

        # 从RAG结果中提取门诊信息
        results = []
        if rag_result and rag_result.get("sources"):
            for source_info in rag_result["sources"][:5]:  # 返回5个结果
                clinic_data = source_info["metadata"].get("original_data", {})
                if clinic_data:
                    # 确保包含所有header字段
                    complete_clinic_data = {
                        "城市": clinic_data.get("城市", ""),
                        "门诊名称": clinic_data.get("门诊名称", ""),
                        "门诊名称英文翻译": clinic_data.get("门诊名称英文翻译", ""),
                        "核心科室": clinic_data.get("核心科室", ""),
                        "服务内容": clinic_data.get("服务内容", ""),
                        "营业时间": clinic_data.get("营业时间", ""),
                        "门诊电话": clinic_data.get("门诊电话", ""),
                        "门诊地址": clinic_data.get("门诊地址", ""),
                        "地址英文翻译": clinic_data.get("地址英文翻译", ""),
                        "免费停车券": clinic_data.get("免费停车券", ""),
                        # 添加RAG增强信息
                        "rag_score": source_info.get("score", 0.0),
                        "rag_confidence": rag_result.get("confidence", 0.0),
                        "search_context": rag_result.get("context", "")[:300] + "..." if rag_result.get("context") else "",
                        "search_query": query
                    }
                    results.append(complete_clinic_data)
        
        # 如果RAG搜索没有结果，回退到向量搜索
        if not results:
            logger.info("RAG搜索无结果，回退到向量搜索")
            try:
                asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, vkm.vector_search(query, sources=["clinics"], max_results=10))
                    search_results = future.result()
            except RuntimeError:
                search_results = asyncio.run(vkm.vector_search(query, sources=["clinics"], max_results=10))
            
            for result in search_results:
                clinic_data = result.metadata.get("original_data", {})
                if clinic_data:
                    # 确保包含所有header字段
                    complete_clinic_data = {
                        "城市": clinic_data.get("城市", ""),
                        "门诊名称": clinic_data.get("门诊名称", ""),
                        "门诊名称英文翻译": clinic_data.get("门诊名称英文翻译", ""),
                        "核心科室": clinic_data.get("核心科室", ""),
                        "服务内容": clinic_data.get("服务内容", ""),
                        "营业时间": clinic_data.get("营业时间", ""),
                        "门诊电话": clinic_data.get("门诊电话", ""),
                        "门诊地址": clinic_data.get("门诊地址", ""),
                        "地址英文翻译": clinic_data.get("地址英文翻译", ""),
                        "免费停车券": clinic_data.get("免费停车券", ""),
                        # 添加向量搜索信息
                        "vector_score": result.score,
                        "search_method": "vector_search",
                        "search_query": query
                    }
                    results.append(complete_clinic_data)
        
        return results
    except Exception as e:
        logger.error(f"门诊RAG搜索失败: {e}")
        return []

def search_supplements(name: Optional[str] = None, function: Optional[str] = None, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """搜索保健品信息 - RAG增强版本，兼容旧接口"""
    import asyncio
    
    vkm = get_vector_knowledge_manager()
    
    # 构建更智能的查询
    query_parts = []
    if name:
        query_parts.append(f"商品名 {name}")
    if function:
        query_parts.append(f"功效 {function}")
    if tags:
        query_parts.append(f"标签 {' '.join(tags)}")
    
    if not query_parts:
        # 如果没有具体条件，返回推荐的热门保健品
        query = "热门保健品 推荐 营养补充"
    else:
        query = " ".join(query_parts)
    
    try:
        # 更安全的异步执行方式
        try:
            loop = asyncio.get_running_loop()
            # 如果已在异步环境中，使用线程池执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, vkm.rag_search(query, sources=["supplements"]))
                rag_result = future.result()
        except RuntimeError:
            # 没有运行中的事件循环，直接运行
            rag_result = asyncio.run(vkm.rag_search(query, sources=["supplements"]))
        
        # 从RAG结果中提取保健品信息
        results = []
        if rag_result and rag_result.get("sources"):
            for source_info in rag_result["sources"][:5]:  # 限制返回5个结果
                supplement_data = source_info["metadata"].get("original_data", {})
                if supplement_data:
                    # 添加RAG增强信息
                    supplement_data["rag_score"] = source_info.get("score", 0.0)
                    supplement_data["rag_confidence"] = rag_result.get("confidence", 0.0)
                    supplement_data["search_context"] = rag_result.get("context", "")[:300] + "..." if rag_result.get("context") else ""
                    supplement_data["recommendation_reason"] = f"基于查询'{query}'的智能匹配"
                    results.append(supplement_data)
        
        # 如果RAG搜索没有结果，回退到向量搜索
        if not results:
            logger.info("保健品RAG搜索无结果，回退到向量搜索")
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, vkm.vector_search(query, sources=["supplements"], max_results=5))
                    search_results = future.result()
            else:
                search_results = asyncio.run(vkm.vector_search(query, sources=["supplements"], max_results=5))
            
            for result in search_results:
                supplement_data = result.metadata.get("original_data", {})
                if supplement_data:
                    supplement_data["vector_score"] = result.score
                    supplement_data["recommendation_reason"] = f"向量匹配相似度: {result.score:.2f}"
                    results.append(supplement_data)
        
        return results
    except Exception as e:
        logger.error(f"保健品RAG搜索失败: {e}")
        return []

def search_qa(question: str) -> List[Dict[str, Any]]:
    """搜索问答信息 - RAG增强版本，兼容旧接口"""
    import asyncio
    
    if not question or not question.strip():
        return []
    
    vkm = get_vector_knowledge_manager()
    
    # 优化查询，添加问答关键词
    enhanced_query = f"问题 {question.strip()}"
    
    try:
        # 更安全的异步执行方式
        try:
            loop = asyncio.get_running_loop()
            # 如果已在异步环境中，使用线程池执行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, vkm.rag_search(enhanced_query, sources=["qa"]))
                rag_result = future.result()
        except RuntimeError:
            # 没有运行中的事件循环，直接运行
            rag_result = asyncio.run(vkm.rag_search(enhanced_query, sources=["qa"]))
        
        # 从RAG结果中提取问答信息
        results = []
        if rag_result and rag_result.get("sources"):
            for source_info in rag_result["sources"][:5]:  # 限制返回5个结果
                qa_data = source_info["metadata"].get("original_data", {})
                if qa_data:
                    # 保持旧接口兼容性，同时添加RAG增强信息
                    qa_data["similarity_score"] = source_info.get("score", 0.0)  # 保持旧字段名
                    qa_data["rag_score"] = source_info.get("score", 0.0)
                    qa_data["rag_confidence"] = rag_result.get("confidence", 0.0)
                    qa_data["search_context"] = rag_result.get("context", "")[:400] + "..." if rag_result.get("context") else ""
                    qa_data["answer_relevance"] = f"与问题的相关度: {source_info.get('score', 0.0):.2f}"
                    qa_data["enhanced_answer"] = _enhance_qa_answer(qa_data.get("回答", ""), rag_result.get("context", ""))
                    results.append(qa_data)
        
        # 如果RAG搜索没有结果，回退到向量搜索
        if not results:
            logger.info("问答RAG搜索无结果，回退到向量搜索")
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, vkm.vector_search(enhanced_query, sources=["qa"], max_results=5))
                    search_results = future.result()
            else:
                search_results = asyncio.run(vkm.vector_search(enhanced_query, sources=["qa"], max_results=5))
            
            for result in search_results:
                qa_data = result.metadata.get("original_data", {})
                if qa_data:
                    qa_data["similarity_score"] = result.score
                    qa_data["vector_score"] = result.score
                    qa_data["answer_relevance"] = f"向量匹配相似度: {result.score:.2f}"
                    results.append(qa_data)
        
        return results
    except Exception as e:
        logger.error(f"问答RAG搜索失败: {e}")
        return []

def _enhance_qa_answer(original_answer: str, context: str) -> str:
    """增强问答回答内容"""
    if not original_answer:
        return ""
    
    if not context or len(context.strip()) < 50:
        return original_answer
    
    # 如果有丰富的上下文，可以提供增强的回答
    enhanced = f"{original_answer}\n\n[相关补充信息]\n{context[:200]}..."
    return enhanced

# 新的异步便捷函数
async def vector_search_supplements(query: str, max_results: int = 5) -> List[SearchResult]:
    """向量搜索保健品"""
    vkm = get_vector_knowledge_manager()
    return await vkm.vector_search(query, sources=["supplements"], max_results=max_results)

async def vector_search_clinics(query: str, max_results: int = 3) -> List[SearchResult]:
    """向量搜索门诊"""
    vkm = get_vector_knowledge_manager()
    return await vkm.vector_search(query, sources=["clinics"], max_results=max_results)

async def vector_search_qa(query: str, max_results: int = 3) -> List[SearchResult]:
    """向量搜索问答"""
    vkm = get_vector_knowledge_manager()
    return await vkm.vector_search(query, sources=["qa"], max_results=max_results)

async def rag_comprehensive_search(query: str) -> Dict[str, Any]:
    """RAG综合搜索"""
    vkm = get_vector_knowledge_manager()
    return await vkm.rag_search(query, sources=["supplements", "clinics", "qa"])

async def performance_test():
    """性能测试和优化验证"""
    logger.info("=== 开始性能测试 ===")
    
    # 创建管理器
    manager = get_vector_knowledge_manager()
    
    # 测试数据
    test_queries = [
        "糖尿病患者适合吃什么保健品",
        "北京哪里有好的中医门诊",
        "提高免疫力的维生素推荐",
        "失眠应该看什么科室",
        "儿童钙片哪个牌子好"
    ]
    
    # 测试批量嵌入生成
    logger.info("\n1. 测试批量嵌入生成性能")
    start_time = time.time()
    embeddings = await manager.get_embeddings(test_queries * 20)  # 100个文本
    batch_time = time.time() - start_time
    logger.info(f"批量嵌入生成 (100个文本): {batch_time:.2f}秒")
    logger.info(f"每个文本平均耗时: {batch_time/100:.3f}秒")
    
    # 测试搜索性能
    logger.info("\n2. 测试搜索性能")
    total_search_time = 0
    for query in test_queries:
        start_time = time.time()
        results = await manager.hybrid_search(
            query=query,
            sources=['supplements', 'clinics'],
            vector_weight=0.7
        )
        search_time = time.time() - start_time
        total_search_time += search_time
        logger.info(f"搜索 '{query}': {search_time:.3f}秒, 结果数: {len(results)}")
    
    avg_search_time = total_search_time / len(test_queries)
    logger.info(f"\n平均搜索时间: {avg_search_time:.3f}秒")
    
    # 测试部门索引构建
    logger.info("\n3. 测试部门索引构建")
    start_time = time.time()
    await manager.build_department_specific_indices('clinics')
    dept_index_time = time.time() - start_time
    logger.info(f"部门索引构建耗时: {dept_index_time:.2f}秒")
    
    # 测试部门特定搜索
    logger.info("\n4. 测试部门特定搜索")
    start_time = time.time()
    dept_results = await manager.search_with_department_index(
        query="糖尿病检查",
        department="内分泌科",
        top_k=5
    )
    dept_search_time = time.time() - start_time
    logger.info(f"部门特定搜索耗时: {dept_search_time:.3f}秒, 结果数: {len(dept_results)}")
    
    # 获取优化统计
    stats = manager.get_stats()
    logger.info(f"\n5. 优化统计:")
    logger.info(f"- 缓存条目数: {len(manager._embedding_cache)}")
    logger.info(f"- 部门索引数: {len(manager.department_indices)}")
    logger.info(f"- TF-IDF向量化器数: {len(manager.tfidf_vectorizers)}")
    logger.info(f"- 总文档数: {stats['total_documents']}")
    
    logger.info("\n=== 性能测试完成 ===")
    
    # 返回性能报告
    return {
        'batch_embedding_time': batch_time,
        'avg_search_time': avg_search_time,
        'dept_index_time': dept_index_time,
        'dept_search_time': dept_search_time,
        'cache_size': len(manager._embedding_cache),
        'dept_indices': len(manager.department_indices)
    }

def get_knowledge_manager():
    """获取全局知识库管理器实例 - 直接返回VectorKnowledgeManager"""
    return get_vector_knowledge_manager()

# ======= RAG上下文增强功能 =======

class RAGContextEnhancer:
    """RAG上下文增强器"""
    
    def __init__(self, vector_manager: VectorKnowledgeManager):
        self.vector_manager = vector_manager
    
    async def enhance_query_context(self, query: str, max_context_results: int = 3) -> Dict[str, Any]:
        """增强查询上下文"""
        try:
            # 执行综合RAG搜索
            rag_result = await self.vector_manager.rag_search(
                query, 
                sources=["supplements", "clinics", "qa"],
                context_window=max_context_results
            )
            
            if not rag_result or not rag_result.get("sources"):
                return {"enhanced_context": "", "confidence": 0.0, "sources": []}
            
            # 构建增强上下文
            context_sections = []
            source_summary = {"supplements": 0, "clinics": 0, "qa": 0}
            
            for source_info in rag_result["sources"]:
                source_type = source_info["source"]
                source_summary[source_type] += 1
                
                # 根据来源类型格式化上下文
                if source_type == "supplements":
                    context_sections.append(f"[保健品信息] {source_info['metadata'].get('original_data', {}).get('商品名', '')} - {source_info['metadata'].get('original_data', {}).get('商品简介/功效', '')}")
                elif source_type == "clinics":
                    context_sections.append(f"[门诊信息] {source_info['metadata'].get('original_data', {}).get('门诊名称', '')} - {source_info['metadata'].get('original_data', {}).get('核心科室', '')}")
                elif source_type == "qa":
                    context_sections.append(f"[问答信息] {source_info['metadata'].get('original_data', {}).get('问题', '')} - {source_info['metadata'].get('original_data', {}).get('回答', '')[:100]}...")
            
            enhanced_context = "\n".join(context_sections)
            
            return {
                "enhanced_context": enhanced_context,
                "confidence": rag_result.get("confidence", 0.0),
                "sources": rag_result["sources"],
                "source_summary": source_summary,
                "total_context_length": len(enhanced_context)
            }
            
        except Exception as e:
            logger.error(f"查询上下文增强失败: {e}")
            return {"enhanced_context": "", "confidence": 0.0, "sources": []}
    
    async def generate_smart_response(self, query: str, context: Dict[str, Any]) -> str:
        """基于增强上下文生成智能回复"""
        try:
            if not context.get("enhanced_context"):
                return f"抱歉，我没有找到关于'{query}'的相关信息。"
            
            confidence = context.get("confidence", 0.0)
            source_summary = context.get("source_summary", {})
            
            response_parts = []
            response_parts.append(f"根据NutriRec知识库的搜索结果（置信度: {confidence:.2f}）：")
            
            if source_summary.get("supplements", 0) > 0:
                response_parts.append(f"• 找到 {source_summary['supplements']} 个相关保健品")
            if source_summary.get("clinics", 0) > 0:
                response_parts.append(f"• 找到 {source_summary['clinics']} 个相关门诊")
            if source_summary.get("qa", 0) > 0:
                response_parts.append(f"• 找到 {source_summary['qa']} 个相关问答")
            
            response_parts.append("\n详细信息：")
            response_parts.append(context["enhanced_context"][:500] + "..." if len(context["enhanced_context"]) > 500 else context["enhanced_context"])
            
            return "\n".join(response_parts)
            
        except Exception as e:
            logger.error(f"智能回复生成失败: {e}")
            return f"关于'{query}'的信息处理出现问题，请稍后重试。"

# 全局RAG上下文增强器
_global_rag_enhancer = None

def get_rag_context_enhancer() -> RAGContextEnhancer:
    """获取全局RAG上下文增强器实例"""
    global _global_rag_enhancer
    
    if _global_rag_enhancer is None:
        _global_rag_enhancer = RAGContextEnhancer(get_vector_knowledge_manager())
    
    return _global_rag_enhancer

# ======= 便捷的RAG接口函数 =======

async def smart_health_search(query: str) -> Dict[str, Any]:
    """智能健康搜索 - 综合RAG功能"""
    enhancer = get_rag_context_enhancer()
    
    # 获取增强上下文
    context = await enhancer.enhance_query_context(query)
    
    # 生成智能回复
    smart_response = await enhancer.generate_smart_response(query, context)
    
    return {
        "query": query,
        "smart_response": smart_response,
        "context": context,
        "timestamp": pd.Timestamp.now().isoformat()
    }

# ======= 初始化和工具函数 =======

def initialize_vector_knowledge_base():
    """初始化向量知识库（同步版本，用于模块加载时）"""
    try:
        vkm = get_vector_knowledge_manager()
        logger.info("向量知识库管理器初始化完成")
        
        # 检查是否需要构建索引
        stats = vkm.get_stats()
        if not any(stats.get("indexes", {}).values()):
            logger.info("检测到没有向量索引，将在后台异步构建...")
            # 不在这里同步构建，因为会阻塞导入
        
        return True
    except Exception as e:
        logger.error(f"向量知识库初始化失败: {e}")
        return False

async def async_initialize_vector_knowledge_base():
    """异步初始化向量知识库"""
    try:
        vkm = get_vector_knowledge_manager()
        await vkm._ensure_indexes_loaded()
        logger.info("向量知识库异步初始化完成")
        return True
    except Exception as e:
        logger.error(f"向量知识库异步初始化失败: {e}")
        return False

def test_vector_search_functionality():
    """测试向量搜索功能"""
    try:
        # 测试保健品搜索
        supplements = search_supplements(name="维生素")
        print(f"保健品搜索测试: 找到 {len(supplements)} 个结果")
        
        # 测试门诊搜索
        clinics = search_clinics(department="内科")
        print(f"门诊搜索测试: 找到 {len(clinics)} 个结果")
        
        # 测试问答搜索
        qa_results = search_qa("什么是营养补充")
        print(f"问答搜索测试: 找到 {len(qa_results)} 个结果")
        
        # 测试VectorKnowledgeManager
        vector_km = get_vector_knowledge_manager()
        stats = vector_km.get_stats()
        print(f"知识库统计: {stats}")
        
        return True
    except Exception as e:
        logger.error(f"向量搜索功能测试失败: {e}")
        return False

# 模块级别的初始化
logger.info("正在初始化NutriRec向量知识库...")
initialize_vector_knowledge_base()

if __name__ == "__main__":
    import asyncio
    
    print("=== NutriRec向量知识库管理器测试 ===")
    
    # 异步初始化
    print("1. 执行异步初始化...")
    asyncio.run(async_initialize_vector_knowledge_base())
    
    # 测试基本功能
    print("2. 测试向量搜索功能...")
    test_vector_search_functionality()
    
    # 测试RAG搜索
    print("3. 测试RAG搜索功能...")
    async def test_rag():
        result = await smart_health_search("推荐一些补钙的保健品")
        print("RAG搜索结果:")
        print(result["smart_response"])
    
    asyncio.run(test_rag())
    
    print("=== 测试完成 ===")