#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SubAgent API服务器
为老服务器提供HTTP API接口，处理医疗咨询请求
运行命令: python3 subagent_api_server.py
访问地址: http://localhost:5000
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import sys
import os
import time
import hashlib
import hmac
from datetime import datetime
import logging
from functools import wraps

# 添加SubAgent系统路径
sys.path.append('.')
try:
    from supplement_subagent.subagent_system import NutriRecSubAgentSystem
except ImportError as e:
    print(f"❌ 无法导入SubAgent系统: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)

app = Flask(__name__)
CORS(app)  # 允许跨域请求

# 配置增强日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler('subagent_api.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 创建专门的访问日志记录器
access_logger = logging.getLogger('access')
access_handler = logging.FileHandler('subagent_access.log', encoding='utf-8')
access_handler.setFormatter(logging.Formatter(
    '%(asctime)s - ACCESS - %(message)s'
))
access_logger.addHandler(access_handler)
access_logger.setLevel(logging.INFO)

# 创建安全日志记录器
security_logger = logging.getLogger('security')
security_handler = logging.FileHandler('subagent_security.log', encoding='utf-8')
security_handler.setFormatter(logging.Formatter(
    '%(asctime)s - SECURITY - %(message)s'
))
security_logger.addHandler(security_handler)
security_logger.setLevel(logging.INFO)

# API配置
API_CONFIG = {
    'secret_key': os.getenv('SUBAGENT_SECRET_KEY', ''),  # 用于验证请求，从环境变量读取
    'max_request_length': 2000,  # 最大请求长度
    'rate_limit': 10,  # 每分钟最大请求数
    'timeout': 120  # API超时时间（秒）
}

# 初始化SubAgent系统
subagent_system = None

def init_subagent():
    """初始化SubAgent系统"""
    global subagent_system
    try:
        subagent_system = NutriRecSubAgentSystem()
        logging.info("✅ SubAgent系统初始化成功")
        return True
    except Exception as e:
        logging.error(f"❌ SubAgent系统初始化失败: {e}")
        return False

def verify_signature(func):
    """验证请求签名的装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 记录请求基本信息
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        user_agent = request.headers.get('User-Agent', 'Unknown')
        request_size = len(request.get_data())
        
        access_logger.info(f"请求开始 - IP: {client_ip}, UA: {user_agent}, 大小: {request_size}字节, 路径: {request.path}")
        
        # 获取请求参数
        signature = request.headers.get('X-Signature')
        timestamp = request.headers.get('X-Timestamp')
        
        if not signature or not timestamp:
            security_logger.warning(f"签名验证失败 - 缺少认证头 - IP: {client_ip}, UA: {user_agent}")
            return jsonify({
                'success': False,
                'error': '缺少签名或时间戳',
                'code': 'MISSING_AUTH'
            }), 401
        
        # 验证时间戳（防止重放攻击）
        try:
            request_time = int(timestamp)
            current_time = int(time.time())
            time_diff = abs(current_time - request_time)
            if time_diff > 300:  # 5分钟有效期
                security_logger.warning(f"时间戳验证失败 - 请求过期 - IP: {client_ip}, 时间差: {time_diff}秒")
                return jsonify({
                    'success': False,
                    'error': '请求已过期',
                    'code': 'EXPIRED_REQUEST'
                }), 401
        except ValueError:
            security_logger.warning(f"时间戳验证失败 - 无效格式 - IP: {client_ip}, 时间戳: {timestamp}")
            return jsonify({
                'success': False,
                'error': '无效的时间戳',
                'code': 'INVALID_TIMESTAMP'
            }), 401
        
        # 验证签名
        data = request.get_data()
        expected_signature = hmac.new(
            API_CONFIG['secret_key'].encode(),
            f"{timestamp}{data.decode('utf-8')}".encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            security_logger.warning(f"签名验证失败 - 签名不匹配 - IP: {client_ip}, 提供签名: {signature[:10]}...")
            return jsonify({
                'success': False,
                'error': '签名验证失败',
                'code': 'INVALID_SIGNATURE'
            }), 401
        
        # 验证成功，记录访问
        access_logger.info(f"签名验证成功 - IP: {client_ip}")
        
        # 执行原函数并记录响应
        start_time = time.time()
        result = func(*args, **kwargs)
        processing_time = time.time() - start_time
        
        # 记录响应信息
        if hasattr(result, 'status_code'):
            status_code = result.status_code
        else:
            status_code = 200
            
        access_logger.info(f"请求完成 - IP: {client_ip}, 状态码: {status_code}, 处理时间: {processing_time:.2f}秒")
        
        return result
    return wrapper

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
    access_logger.info(f"健康检查请求 - IP: {client_ip}")
    
    return jsonify({
        'status': 'healthy',
        'service': 'SubAgent API',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'subagent_ready': subagent_system is not None
    })

@app.route('/consultation', methods=['POST'])
@verify_signature
def process_consultation():
    """处理医疗咨询请求"""
    try:
        # 检查SubAgent系统状态
        if subagent_system is None:
            return jsonify({
                'success': False,
                'error': 'SubAgent系统未初始化',
                'code': 'SYSTEM_NOT_READY'
            }), 503
        
        # 获取请求数据
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': '请求数据为空',
                'code': 'EMPTY_REQUEST'
            }), 400
        
        # 验证必需参数
        required_fields = ['user_input', 'user_id']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'缺少必需参数: {field}',
                    'code': 'MISSING_PARAMETER'
                }), 400
        
        user_input = data['user_input']
        user_id = data['user_id']
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        
        # 记录用户请求详情
        input_preview = user_input[:50] + ('...' if len(user_input) > 50 else '')
        access_logger.info(f"医疗咨询请求 - 用户: {user_id}, IP: {client_ip}, 输入预览: '{input_preview}', 字符数: {len(user_input)}")
        
        # 验证输入长度
        if len(user_input) > API_CONFIG['max_request_length']:
            security_logger.warning(f"输入长度超限 - 用户: {user_id}, IP: {client_ip}, 长度: {len(user_input)}")
            return jsonify({
                'success': False,
                'error': f'输入内容过长，最大长度: {API_CONFIG["max_request_length"]}',
                'code': 'INPUT_TOO_LONG'
            }), 400
        
        # 获取API配置（使用默认值或请求中的配置）
        api_config = {
            'provider': data.get('provider', 'deepseek'),
            'model_name': data.get('model_name', 'deepseek-chat'),
            'api_key': data.get('api_key', os.getenv('API_KEY')),
            'base_url': data.get('base_url'),
            'max_tokens': data.get('max_tokens', 8000),
            'temperature': data.get('temperature', 0.7),
            'timeout': data.get('timeout', API_CONFIG['timeout']),
            'max_workers': data.get('max_workers', 6)
        }
        
        # 记录API配置信息（隐藏敏感信息）
        safe_config = api_config.copy()
        if safe_config['api_key']:
            safe_config['api_key'] = safe_config['api_key'][:8] + '...' if len(safe_config['api_key']) > 8 else '***'
        
        access_logger.info(f"API配置 - 用户: {user_id}, 提供商: {api_config['provider']}, 模型: {api_config['model_name']}, 工作线程: {api_config['max_workers']}")
        
        # 调用SubAgent系统
        start_time = time.time()
        
        async def process_request():
            return await subagent_system.process_consultation(
                user_input=user_input,
                provider=api_config['provider'],
                model_name=api_config['model_name'],
                api_key=api_config['api_key'],
                base_url=api_config['base_url'],
                max_tokens=api_config['max_tokens'],
                temperature=api_config['temperature'],
                timeout=api_config['timeout'],
                max_workers=api_config['max_workers']
            )
        
        # 运行异步任务
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(process_request())
        finally:
            loop.close()
        
        processing_time = time.time() - start_time
        
        # 记录详细结果日志
        if result['status'] == 'success':
            recommendation_length = len(result.get('final_recommendation', ''))
            access_logger.info(f"✅ 咨询处理成功 - 用户: {user_id}, IP: {client_ip}, 耗时: {processing_time:.2f}s, 回复长度: {recommendation_length}字符")
            logging.info(f"✅ 咨询处理成功 - 用户: {user_id}, 耗时: {processing_time:.2f}s")
        else:
            error_msg = result.get('message', 'Unknown')
            access_logger.error(f"❌ 咨询处理失败 - 用户: {user_id}, IP: {client_ip}, 耗时: {processing_time:.2f}s, 错误: {error_msg}")
            logging.warning(f"⚠️ 咨询处理失败 - 用户: {user_id}, 错误: {error_msg}")
        
        # 返回结果
        response = {
            'success': result['status'] == 'success',
            'data': {
                'recommendation': result.get('final_recommendation', ''),
                'processing_time': round(processing_time, 2),
                'timestamp': datetime.now().isoformat()
            }
        }
        
        if result['status'] != 'success':
            response['error'] = result.get('message', '处理失败')
            response['code'] = 'PROCESSING_ERROR'
        
        return jsonify(response)
        
    except Exception as e:
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        user_id = request.get_json().get('user_id', 'unknown') if request.get_json() else 'unknown'
        
        access_logger.error(f"❌ API处理异常 - 用户: {user_id}, IP: {client_ip}, 异常: {str(e)}")
        logging.error(f"❌ API处理异常: {str(e)}", exc_info=True)
        
        return jsonify({
            'success': False,
            'error': '服务器内部错误',
            'code': 'INTERNAL_ERROR'
        }), 500

@app.route('/status', methods=['GET'])
def get_status():
    """获取系统状态"""
    return jsonify({
        'service': 'SubAgent API Server',
        'version': '1.0.0',
        'status': 'running',
        'subagent_initialized': subagent_system is not None,
        'config': {
            'max_request_length': API_CONFIG['max_request_length'],
            'rate_limit': API_CONFIG['rate_limit'],
            'timeout': API_CONFIG['timeout']
        },
        'timestamp': datetime.now().isoformat()
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': '接口不存在',
        'code': 'NOT_FOUND'
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': '服务器内部错误',
        'code': 'INTERNAL_ERROR'
    }), 500

if __name__ == '__main__':
    print("🚀 启动SubAgent API服务器...")
    print("=" * 50)
    
    # 初始化SubAgent系统
    if not init_subagent():
        print("❌ SubAgent系统初始化失败，服务器将无法处理咨询请求")
        print("请检查 supplement_subagent 目录和依赖包是否正确安装")
        sys.exit(1)
    
    print("✅ SubAgent系统初始化完成")
    print(f"🔑 API密钥: {API_CONFIG['secret_key'][:20]}...")
    print(f"📊 配置信息:")
    print(f"   - 最大请求长度: {API_CONFIG['max_request_length']} 字符")
    print(f"   - 请求频率限制: {API_CONFIG['rate_limit']} 次/分钟")
    print(f"   - 超时时间: {API_CONFIG['timeout']} 秒")
    print(f"🌐 API接口:")
    print(f"   - 健康检查: GET  http://localhost:5001/health")
    print(f"   - 医疗咨询: POST http://localhost:5001/consultation")
    print(f"   - 系统状态: GET  http://localhost:5001/status")
    print("=" * 50)
    
    # 启动Flask服务器
    try:
        app.run(
            host='0.0.0.0',  # 允许外部访问
            port=5001,
            debug=False,  # 生产环境不开启debug
            threaded=True   # 支持多线程
        )
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except Exception as e:
        print(f"❌ 服务器启动失败: {e}") 