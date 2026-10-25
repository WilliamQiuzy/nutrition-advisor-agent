#!/usr/bin/env python3
"""
简化的门诊搜索测试
直接展示搜索结果，包含完整信息
"""

import asyncio
import time
import json
import pandas as pd
from datetime import datetime

from vector_knowledge_manager import VectorKnowledgeManager

# 配置日志
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'
)
logger = logging.getLogger(__name__)


async def test_clinics_search():
    """测试门诊搜索功能"""
    manager = VectorKnowledgeManager()
    
    # 确保索引已加载
    await manager._ensure_indexes_loaded()
    
    # 先分析一下CSV数据
    logger.info("="*80)
    logger.info("分析门诊数据")
    logger.info("="*80)
    
    clinics_file = manager.knowledge_base_path / "clinics.csv"
    if clinics_file.exists():
        df = pd.read_csv(clinics_file)
        logger.info(f"\n总记录数: {len(df)}")
        logger.info(f"字段列表: {', '.join(df.columns.tolist())}")
        
        # 显示前3条数据
        logger.info("\n前3条数据示例:")
        for idx, row in df.head(3).iterrows():
            logger.info(f"\n记录 {idx+1}:")
            logger.info(f"  门诊名称: {row['门诊名称']}")
            logger.info(f"  核心科室: {row['核心科室']}")
            logger.info(f"  城市: {row['城市']}")
            logger.info(f"  服务内容: {row['服务内容'][:50]}...")
            logger.info(f"  门诊地址: {row['门诊地址']}")
    
    # 测试查询列表
    test_queries = [
        "儿科",
        "皮肤科看痘痘",
        "广州眼科配镜",
        "儿童生长发育",
        "体育西路门诊",
        "周末营业的儿科"
    ]
    
    logger.info("\n" + "="*80)
    logger.info("开始搜索测试")
    logger.info("="*80)
    
    results_data = []
    
    for query in test_queries:
        logger.info(f"\n{'='*60}")
        logger.info(f"查询: {query}")
        logger.info(f"{'='*60}")
        
        # 1. 基础向量搜索
        logger.info("\n【向量搜索】")
        start_time = time.time()
        vector_results = await manager.vector_search(
            query=query,
            sources=['clinics'],
            max_results=5
        )
        vector_time = time.time() - start_time
        logger.info(f"耗时: {vector_time:.3f}秒, 结果数: {len(vector_results)}")
        
        # 显示结果
        for i, result in enumerate(vector_results[:3]):
            logger.info(f"\n结果 {i+1} (得分: {result.score:.3f}):")
            if hasattr(result, 'metadata'):
                meta = result.metadata
                original = meta.get('original_data', {})
                logger.info(f"  门诊: {meta.get('clinic_name', original.get('门诊名称', 'N/A'))}")
                logger.info(f"  科室: {meta.get('department', original.get('核心科室', 'N/A'))}")
                logger.info(f"  城市: {meta.get('city', original.get('城市', 'N/A'))}")
                logger.info(f"  地址: {original.get('门诊地址', 'N/A')}")
                logger.info(f"  服务: {original.get('服务内容', 'N/A')[:100]}...")
                logger.info(f"  电话: {original.get('门诊电话', 'N/A')}")
            logger.info(f"  内容: {result.content[:100]}...")
        
        # 2. 混合搜索（带查询扩展）
        logger.info("\n【混合搜索】")
        expanded_query = manager._expand_query(query, 'clinics')
        logger.info(f"扩展查询: {expanded_query}")
        
        start_time = time.time()
        hybrid_results = await manager.hybrid_search(
            query=query,
            sources=['clinics']
        )
        hybrid_time = time.time() - start_time
        logger.info(f"耗时: {hybrid_time:.3f}秒, 结果数: {len(hybrid_results)}")
        
        # 保存结果数据
        query_result = {
            "query": query,
            "expanded_query": expanded_query,
            "vector_search": {
                "time": vector_time,
                "count": len(vector_results),
                "top_results": []
            },
            "hybrid_search": {
                "time": hybrid_time,
                "count": len(hybrid_results),
                "top_results": []
            }
        }
        
        # 收集向量搜索结果
        for result in vector_results[:3]:
            if hasattr(result, 'metadata'):
                meta = result.metadata
                original = meta.get('original_data', {})
                query_result["vector_search"]["top_results"].append({
                    "score": float(result.score),
                    "门诊名称": meta.get('clinic_name', original.get('门诊名称', 'N/A')),
                    "核心科室": meta.get('department', original.get('核心科室', 'N/A')),
                    "城市": meta.get('city', original.get('城市', 'N/A')),
                    "门诊地址": original.get('门诊地址', 'N/A'),
                    "服务内容": original.get('服务内容', 'N/A'),
                    "营业时间": original.get('营业时间', 'N/A'),
                    "门诊电话": original.get('门诊电话', 'N/A')
                })
        
        # 收集混合搜索结果
        for result in hybrid_results[:3]:
            if hasattr(result, 'metadata'):
                meta = result.metadata
                original = meta.get('original_data', {})
                query_result["hybrid_search"]["top_results"].append({
                    "score": float(result.score),
                    "门诊名称": meta.get('clinic_name', original.get('门诊名称', 'N/A')),
                    "核心科室": meta.get('department', original.get('核心科室', 'N/A')),
                    "城市": meta.get('city', original.get('城市', 'N/A')),
                    "门诊地址": original.get('门诊地址', 'N/A'),
                    "服务内容": original.get('服务内容', 'N/A'),
                    "营业时间": original.get('营业时间', 'N/A'),
                    "门诊电话": original.get('门诊电话', 'N/A')
                })
        
        results_data.append(query_result)
        
        # 短暂延迟
        await asyncio.sleep(0.1)
    
    # 保存结果
    output_file = f"./reports/clinics_search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_time": datetime.now().isoformat(),
            "total_queries": len(test_queries),
            "results": results_data
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n\n测试完成！详细结果已保存到: {output_file}")
    
    # 简单统计
    logger.info("\n性能统计:")
    avg_vector_time = sum(r["vector_search"]["time"] for r in results_data) / len(results_data)
    avg_hybrid_time = sum(r["hybrid_search"]["time"] for r in results_data) / len(results_data)
    logger.info(f"向量搜索平均耗时: {avg_vector_time:.3f}秒")
    logger.info(f"混合搜索平均耗时: {avg_hybrid_time:.3f}秒")


if __name__ == "__main__":
    asyncio.run(test_clinics_search())