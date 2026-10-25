#!/usr/bin/env python3
"""
配置管理系统
支持环境变量、配置文件和动态配置更新
"""

import os
import json
import yaml
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass, asdict
from pathlib import Path
import logging
from datetime import datetime
from enum import Enum


class Environment(Enum):
    """环境类型"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


@dataclass
class DatabaseConfig:
    """数据库配置"""
    host: str = "localhost"
    port: int = 5432
    username: str = "postgres"
    password: str = ""
    database: str = "nutrirec_healthcare"
    ssl_mode: str = "prefer"
    max_connections: int = 20


@dataclass
class SecurityConfig:
    """安全配置"""
    max_requests_per_hour: int = 100
    request_timeout: int = 30
    enable_rate_limiting: bool = True
    enable_content_validation: bool = True
    audit_log_retention_days: int = 90
    encryption_key: Optional[str] = None


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    log_dir: str = "logs"
    max_file_size_mb: int = 50
    backup_count: int = 10
    enable_json_format: bool = True
    enable_console_output: bool = True


@dataclass
class APIConfig:
    """API配置"""
    # AI服务配置
    ai_provider: str = "deepseek"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4"
    openai_base_url: str = "https://api.openai.com/v1"
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    
    # 通用AI配置
    max_tokens: int = 2000
    temperature: float = 0.7
    timeout: int = 60
    max_retries: int = 3
    
    # FHIR配置
    fhir_base_url: str = "https://hapi.fhir.org/baseR4"


@dataclass
class PerformanceConfig:
    """性能配置"""
    max_concurrent_requests: int = 10
    request_queue_size: int = 100
    cache_ttl_seconds: int = 3600
    enable_performance_monitoring: bool = True
    slow_query_threshold_seconds: float = 5.0


@dataclass
class NutriRecConfig:
    """NutriRec医疗系统完整配置"""
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    version: str = "1.0.0"
    
    # 子配置
    database: DatabaseConfig = None
    security: SecurityConfig = None
    logging: LoggingConfig = None
    api: APIConfig = None
    performance: PerformanceConfig = None
    
    # 自定义配置
    custom: Dict[str, Any] = None
    
    def __post_init__(self):
        """初始化后处理"""
        if self.database is None:
            self.database = DatabaseConfig()
        if self.security is None:
            self.security = SecurityConfig()
        if self.logging is None:
            self.logging = LoggingConfig()
        if self.api is None:
            self.api = APIConfig()
        if self.performance is None:
            self.performance = PerformanceConfig()
        if self.custom is None:
            self.custom = {}


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_dir: str = "config", env_file: str = ".env"):
        self.config_dir = Path(config_dir)
        self.env_file = Path(env_file)
        self.logger = logging.getLogger(__name__)
        
        # 当前配置
        self._config: Optional[NutriRecConfig] = None
        self._config_sources = []  # 记录配置来源
        
        # 配置文件路径
        self.base_config_file = self.config_dir / "base.yaml"
        self.env_config_files = {
            Environment.DEVELOPMENT: self.config_dir / "environments" / "development.yaml",
            Environment.STAGING: self.config_dir / "environments" / "staging.yaml", 
            Environment.PRODUCTION: self.config_dir / "environments" / "production.yaml",
            Environment.TESTING: self.config_dir / "environments" / "testing.yaml"
        }
    
    def load_config(self, environment: Optional[Environment] = None) -> NutriRecConfig:
        """加载配置"""
        if environment is None:
            environment = self._detect_environment()
        
        self.logger.info(f"加载配置，环境: {environment.value}")
        
        # 1. 从默认值开始
        config_data = self._get_default_config()
        self._config_sources.append("defaults")
        
        # 2. 加载基础配置文件
        if self.base_config_file.exists():
            base_config = self._load_yaml_file(self.base_config_file)
            config_data = self._merge_config(config_data, base_config)
            self._config_sources.append(f"file:{self.base_config_file}")
        
        # 3. 加载环境特定配置
        env_config_file = self.env_config_files.get(environment)
        if env_config_file and env_config_file.exists():
            env_config = self._load_yaml_file(env_config_file)
            config_data = self._merge_config(config_data, env_config)
            self._config_sources.append(f"file:{env_config_file}")
        
        # 4. 加载环境变量
        env_config = self._load_from_environment()
        config_data = self._merge_config(config_data, env_config)
        self._config_sources.append("environment_variables")
        
        # 5. 加载.env文件
        if self.env_file.exists():
            dotenv_config = self._load_dotenv_file()
            config_data = self._merge_config(config_data, dotenv_config)
            self._config_sources.append(f"file:{self.env_file}")
        
        # 6. 创建配置对象
        self._config = self._create_config_object(config_data, environment)
        
        self.logger.info(f"配置加载完成，来源: {', '.join(self._config_sources)}")
        return self._config
    
    def _detect_environment(self) -> Environment:
        """检测运行环境"""
        env_name = os.getenv("NUTRIREC_ENV", os.getenv("ENV", "development")).lower()
        
        env_mapping = {
            "dev": Environment.DEVELOPMENT,
            "development": Environment.DEVELOPMENT,
            "staging": Environment.STAGING,
            "stage": Environment.STAGING,
            "prod": Environment.PRODUCTION,
            "production": Environment.PRODUCTION,
            "test": Environment.TESTING,
            "testing": Environment.TESTING
        }
        
        return env_mapping.get(env_name, Environment.DEVELOPMENT)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "debug": False,
            "version": "1.0.0",
            "database": {
                "host": "localhost",
                "port": 5432,
                "username": "postgres",
                "password": "",
                "database": "nutrirec_healthcare",
                "ssl_mode": "prefer",
                "max_connections": 20
            },
            "security": {
                "max_requests_per_hour": 100,
                "request_timeout": 30,
                "enable_rate_limiting": True,
                "enable_content_validation": True,
                "audit_log_retention_days": 90
            },
            "logging": {
                "level": "INFO",
                "log_dir": "logs",
                "max_file_size_mb": 50,
                "backup_count": 10,
                "enable_json_format": True,
                "enable_console_output": True
            },
            "api": {
                "openai_model": "gpt-3.5-turbo",
                "max_tokens": 2000,
                "temperature": 0.7,
                "timeout": 30,
                "fhir_base_url": "https://hapi.fhir.org/baseR4"
            },
            "performance": {
                "max_concurrent_requests": 10,
                "request_queue_size": 100,
                "cache_ttl_seconds": 3600,
                "enable_performance_monitoring": True,
                "slow_query_threshold_seconds": 5.0
            }
        }
    
    def _load_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """加载YAML配置文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.error(f"加载配置文件失败 {file_path}: {e}")
            return {}
    
    def _load_from_environment(self) -> Dict[str, Any]:
        """从环境变量加载配置"""
        env_config = {}
        
        # 环境变量映射
        env_mappings = {
            # 基础配置
            "NUTRIREC_DEBUG": ("debug", self._parse_bool),
            "NUTRIREC_VERSION": ("version", str),
            
            # 数据库配置
            "DB_HOST": ("database.host", str),
            "DB_PORT": ("database.port", int),
            "DB_USERNAME": ("database.username", str),
            "DB_PASSWORD": ("database.password", str),
            "DB_DATABASE": ("database.database", str),
            "DB_SSL_MODE": ("database.ssl_mode", str),
            "DB_MAX_CONNECTIONS": ("database.max_connections", int),
            
            # API配置
            "AI_PROVIDER": ("api.ai_provider", str),
            "OPENAI_API_KEY": ("api.openai_api_key", str),
            "OPENAI_MODEL": ("api.openai_model", str),
            "OPENAI_BASE_URL": ("api.openai_base_url", str),
            "DEEPSEEK_API_KEY": ("api.deepseek_api_key", str),
            "DEEPSEEK_MODEL": ("api.deepseek_model", str),
            "DEEPSEEK_BASE_URL": ("api.deepseek_base_url", str),
            "AI_MAX_TOKENS": ("api.max_tokens", int),
            "AI_TEMPERATURE": ("api.temperature", float),
            "AI_TIMEOUT": ("api.timeout", int),
            "AI_MAX_RETRIES": ("api.max_retries", int),
            "FHIR_BASE_URL": ("api.fhir_base_url", str),
            
            # 安全配置
            "MAX_REQUESTS_PER_HOUR": ("security.max_requests_per_hour", int),
            "REQUEST_TIMEOUT": ("security.request_timeout", int),
            "ENABLE_RATE_LIMITING": ("security.enable_rate_limiting", self._parse_bool),
            "ENABLE_CONTENT_VALIDATION": ("security.enable_content_validation", self._parse_bool),
            "ENCRYPTION_KEY": ("security.encryption_key", str),
            
            # 日志配置
            "LOG_LEVEL": ("logging.level", str),
            "LOG_DIR": ("logging.log_dir", str),
            "LOG_MAX_FILE_SIZE_MB": ("logging.max_file_size_mb", int),
            "LOG_BACKUP_COUNT": ("logging.backup_count", int),
            "ENABLE_JSON_FORMAT": ("logging.enable_json_format", self._parse_bool),
            "ENABLE_CONSOLE_OUTPUT": ("logging.enable_console_output", self._parse_bool),
            
            # 性能配置
            "MAX_CONCURRENT_REQUESTS": ("performance.max_concurrent_requests", int),
            "REQUEST_QUEUE_SIZE": ("performance.request_queue_size", int),
            "CACHE_TTL_SECONDS": ("performance.cache_ttl_seconds", int),
            "ENABLE_PERFORMANCE_MONITORING": ("performance.enable_performance_monitoring", self._parse_bool),
            "SLOW_QUERY_THRESHOLD": ("performance.slow_query_threshold_seconds", float)
        }
        
        for env_var, (config_path, converter) in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    converted_value = converter(value)
                    self._set_nested_value(env_config, config_path, converted_value)
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"环境变量 {env_var} 转换失败: {e}")
        
        return env_config
    
    def _load_dotenv_file(self) -> Dict[str, Any]:
        """加载.env文件"""
        env_config = {}
        
        try:
            with open(self.env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            key = key.strip()
                            value = value.strip().strip('"\'')
                            
                            # 临时设置环境变量，然后通过环境变量处理
                            original_value = os.getenv(key)
                            os.environ[key] = value
                            
                            # 使用环境变量处理逻辑
                            temp_config = self._load_from_environment()
                            env_config = self._merge_config(env_config, temp_config)
                            
                            # 恢复原始环境变量
                            if original_value is not None:
                                os.environ[key] = original_value
                            else:
                                os.environ.pop(key, None)
                                
        except Exception as e:
            self.logger.error(f"加载.env文件失败: {e}")
        
        return env_config
    
    def _parse_bool(self, value: str) -> bool:
        """解析布尔值"""
        return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
    
    def _set_nested_value(self, config: Dict[str, Any], path: str, value: Any):
        """设置嵌套配置值"""
        keys = path.split('.')
        current = config
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """合并配置"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _create_config_object(self, config_data: Dict[str, Any], environment: Environment) -> NutriRecConfig:
        """创建配置对象"""
        try:
            # 设置环境
            config_data["environment"] = environment
            
            # 创建子配置对象
            database_config = DatabaseConfig(**config_data.get("database", {}))
            security_config = SecurityConfig(**config_data.get("security", {}))
            logging_config = LoggingConfig(**config_data.get("logging", {}))
            api_config = APIConfig(**config_data.get("api", {}))
            performance_config = PerformanceConfig(**config_data.get("performance", {}))
            
            # 提取其他配置
            other_keys = {"database", "security", "logging", "api", "performance", "environment"}
            custom_config = {k: v for k, v in config_data.items() if k not in other_keys}
            
            return NutriRecConfig(
                environment=environment,
                debug=config_data.get("debug", False),
                version=config_data.get("version", "1.0.0"),
                database=database_config,
                security=security_config,
                logging=logging_config,
                api=api_config,
                performance=performance_config,
                custom=custom_config
            )
            
        except Exception as e:
            self.logger.error(f"创建配置对象失败: {e}")
            # 返回默认配置
            return NutriRecConfig(environment=environment)
    
    def get_config(self) -> NutriRecConfig:
        """获取当前配置"""
        if self._config is None:
            self._config = self.load_config()
        return self._config
    
    def reload_config(self, environment: Optional[Environment] = None) -> NutriRecConfig:
        """重新加载配置"""
        self._config_sources.clear()
        return self.load_config(environment)
    
    def save_config(self, config: NutriRecConfig, file_path: Optional[Path] = None):
        """保存配置到文件"""
        if file_path is None:
            file_path = self.config_dir / f"generated_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
        
        try:
            # 确保目录存在
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 转换为字典
            config_dict = asdict(config)
            
            # 移除None值
            config_dict = self._remove_none_values(config_dict)
            
            # 保存为YAML
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True, indent=2)
            
            self.logger.info(f"配置已保存到: {file_path}")
            
        except Exception as e:
            self.logger.error(f"保存配置失败: {e}")
            raise
    
    def _remove_none_values(self, data: Any) -> Any:
        """递归移除None值"""
        if isinstance(data, dict):
            return {k: self._remove_none_values(v) for k, v in data.items() if v is not None}
        elif isinstance(data, list):
            return [self._remove_none_values(item) for item in data if item is not None]
        else:
            return data
    
    def validate_config(self, config: NutriRecConfig) -> List[str]:
        """验证配置"""
        errors = []
        
        # 验证API配置
        if not config.api.openai_api_key:
            errors.append("缺少OpenAI API密钥")
        
        if config.api.max_tokens <= 0:
            errors.append("max_tokens必须大于0")
        
        if not (0 <= config.api.temperature <= 2):
            errors.append("temperature必须在0-2之间")
        
        # 验证安全配置
        if config.security.max_requests_per_hour <= 0:
            errors.append("max_requests_per_hour必须大于0")
        
        if config.security.request_timeout <= 0:
            errors.append("request_timeout必须大于0")
        
        # 验证数据库配置
        if not config.database.host:
            errors.append("数据库主机不能为空")
        
        if not (1 <= config.database.port <= 65535):
            errors.append("数据库端口必须在1-65535之间")
        
        # 验证性能配置
        if config.performance.max_concurrent_requests <= 0:
            errors.append("max_concurrent_requests必须大于0")
        
        return errors
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        if self._config is None:
            return {"error": "配置未加载"}
        
        return {
            "environment": self._config.environment.value,
            "debug": self._config.debug,
            "version": self._config.version,
            "config_sources": self._config_sources,
            "validation_errors": self.validate_config(self._config),
            "loaded_at": datetime.now().isoformat()
        }


# 全局配置管理器实例
_global_config_manager = None


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    global _global_config_manager
    if _global_config_manager is None:
        _global_config_manager = ConfigManager()
    return _global_config_manager


def get_config() -> NutriRecConfig:
    """获取当前配置的便捷方法"""
    return get_config_manager().get_config()


def get_ai_config() -> Dict[str, Any]:
    """获取AI配置用于Autogen"""
    config = get_config()
    api_config = config.api
    
    # 根据AI提供商返回相应配置
    if api_config.ai_provider == "deepseek":
        api_key = api_config.deepseek_api_key
        model = api_config.deepseek_model
        base_url = api_config.deepseek_base_url
    else:  # 默认使用OpenAI
        api_key = api_config.openai_api_key
        model = api_config.openai_model
        base_url = api_config.openai_base_url
    
    if not api_key:
        raise ValueError(f"缺少{api_config.ai_provider}的API密钥")
    
    return {
        "config_list": [
            {
                "model": model,
                "api_key": api_key,
                "base_url": base_url,
                "temperature": api_config.temperature,
                "max_tokens": api_config.max_tokens,
                "timeout": api_config.timeout
            }
        ],
        "timeout": api_config.timeout,
        "cache_seed": None,
        "functions": []
    }


# 配置验证装饰器
def require_config(*required_fields):
    """要求特定配置字段的装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            config = get_config()
            
            # 检查必需的配置字段
            for field_path in required_fields:
                value = config
                for field in field_path.split('.'):
                    value = getattr(value, field, None)
                    if value is None:
                        raise ValueError(f"缺少必需的配置: {field_path}")
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator 