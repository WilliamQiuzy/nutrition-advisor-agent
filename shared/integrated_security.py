"""
Integrated Security System for Healthcare AI
Combines all security components into a unified, easy-to-use interface
"""

import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Tuple, Any, Callable
from datetime import datetime
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
import uuid

import redis
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, Field

# Import all security components
try:
    from .security_gateway import (
        SecurityGateway, SecurityMiddleware, ThreatLevel, 
        RequestType, RateLimitConfig
    )
except ImportError:
    from security_gateway import (
        SecurityGateway, SecurityMiddleware, ThreatLevel, 
        RequestType, RateLimitConfig
    )

try:
    from .cost_monitoring import (
        CostMonitor, CostTracker, ModelPricing, 
        AlertLevel, CostAlert
    )
except ImportError:
    from cost_monitoring import (
        CostMonitor, CostTracker, ModelPricing, 
        AlertLevel, CostAlert
    )

try:
    from .audit_logging import (
        AuditLogger, AuditEvent, EventType, Severity,
        get_audit_logger
    )
except ImportError:
    from audit_logging import (
        AuditLogger, AuditEvent, EventType, Severity,
        get_audit_logger
    )

try:
    from .content_security import (
        ContentSecurityFilter, ContentType, MedicalDisclaimer,
        ResponseFormatter
    )
except ImportError:
    from content_security import (
        ContentSecurityFilter, ContentType, MedicalDisclaimer,
        ResponseFormatter
    )

try:
    from .agent_isolation import (
        SecureAgentExecutor, IsolationLevel, AgentPermissions,
        Permission, isolated_agent
    )
except ImportError:
    from agent_isolation import (
        SecureAgentExecutor, IsolationLevel, AgentPermissions,
        Permission, isolated_agent
    )

try:
    from .response_validation import (
        ResponseValidator, AgentResponse, ValidationRule,
        validate_multi_agent_responses
    )
except ImportError:
    from response_validation import (
        ResponseValidator, AgentResponse, ValidationRule,
        validate_multi_agent_responses
    )

logger = logging.getLogger(__name__)


@dataclass
class SecurityConfig:
    """Unified security configuration"""
    # Feature toggles
    enable_rate_limiting: bool = True
    enable_cost_monitoring: bool = True
    enable_audit_logging: bool = True
    enable_content_filtering: bool = True
    enable_agent_isolation: bool = True
    enable_response_validation: bool = True
    
    # Component configurations
    rate_limit_config: Optional[RateLimitConfig] = None
    isolation_level: IsolationLevel = IsolationLevel.STANDARD
    
    # Redis configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: Optional[str] = None
    
    # Encryption keys
    audit_encryption_key: Optional[str] = None
    
    # Monitoring
    enable_metrics: bool = True
    metrics_port: int = 9090
    
    @classmethod
    def from_env(cls) -> "SecurityConfig":
        """Create config from environment variables"""
        return cls(
            enable_rate_limiting=os.getenv("SECURITY_RATE_LIMITING", "true").lower() == "true",
            enable_cost_monitoring=os.getenv("SECURITY_COST_MONITORING", "true").lower() == "true",
            enable_audit_logging=os.getenv("SECURITY_AUDIT_LOGGING", "true").lower() == "true",
            enable_content_filtering=os.getenv("SECURITY_CONTENT_FILTERING", "true").lower() == "true",
            enable_agent_isolation=os.getenv("SECURITY_AGENT_ISOLATION", "true").lower() == "true",
            enable_response_validation=os.getenv("SECURITY_RESPONSE_VALIDATION", "true").lower() == "true",
            isolation_level=IsolationLevel[os.getenv("SECURITY_ISOLATION_LEVEL", "STANDARD")],
            redis_host=os.getenv("REDIS_HOST", "redis"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_password=os.getenv("REDIS_PASSWORD"),
            audit_encryption_key=os.getenv("AUDIT_ENCRYPTION_KEY"),
            enable_metrics=os.getenv("SECURITY_METRICS", "true").lower() == "true",
            metrics_port=int(os.getenv("METRICS_PORT", "9090"))
        )


class IntegratedSecuritySystem:
    """
    Unified security system that integrates all security components
    Provides a single interface for comprehensive security management
    """
    
    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig.from_env()
        
        # Initialize Redis client
        self.redis_client = self._init_redis()
        
        # Initialize components
        self.security_gateway = None
        self.cost_monitor = None
        self.audit_logger = None
        self.content_filter = None
        self.agent_executor = None
        self.response_validator = None
        
        self._initialize_components()
        
        # Metrics collection
        self.metrics = {
            "requests_processed": 0,
            "requests_blocked": 0,
            "total_cost": 0.0,
            "security_events": 0
        }
    
    def _init_redis(self) -> Optional[redis.Redis]:
        """Initialize Redis client"""
        if not any([
            self.config.enable_rate_limiting,
            self.config.enable_cost_monitoring,
            self.config.enable_audit_logging
        ]):
            return None
        
        try:
            client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                password=self.config.redis_password,
                decode_responses=True,
                socket_connect_timeout=5
            )
            client.ping()
            logger.info("Redis connection established for security system")
            return client
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Some features will use in-memory fallback.")
            return None
    
    def _initialize_components(self):
        """Initialize all security components based on configuration"""
        if self.config.enable_rate_limiting:
            self.security_gateway = SecurityGateway(
                redis_client=self.redis_client,
                rate_limit_config=self.config.rate_limit_config,
                enable_logging=self.config.enable_audit_logging
            )
            logger.info("Security Gateway initialized")
        
        if self.config.enable_cost_monitoring:
            self.cost_monitor = CostMonitor(
                redis_client=self.redis_client,
                enable_persistence=True
            )
            logger.info("Cost Monitor initialized")
        
        if self.config.enable_audit_logging:
            self.audit_logger = AuditLogger(
                redis_client=self.redis_client,
                encryption_key=self.config.audit_encryption_key
            )
            logger.info("Audit Logger initialized")
        
        if self.config.enable_content_filtering:
            self.content_filter = ContentSecurityFilter(
                enable_medical_disclaimers=True,
                enable_sensitive_content_filtering=True,
                enable_brand_protection=True
            )
            logger.info("Content Security Filter initialized")
        
        if self.config.enable_agent_isolation:
            self.agent_executor = SecureAgentExecutor(
                isolation_level=self.config.isolation_level,
                enable_monitoring=True
            )
            logger.info(f"Agent Executor initialized with {self.config.isolation_level.name} isolation")
        
        if self.config.enable_response_validation:
            self.response_validator = ResponseValidator(
                enable_conflict_resolution=True,
                min_agreement_threshold=0.7
            )
            logger.info("Response Validator initialized")
    
    async def process_request(
        self,
        request_id: str,
        user_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Process a request through all security layers
        
        Returns:
            Tuple of (is_allowed, rejection_reason, security_context)
        """
        security_context = {
            "request_id": request_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "checks_performed": []
        }
        
        # 1. Security Gateway Check
        if self.security_gateway:
            is_allowed, reason, threat_level = await self.security_gateway.check_request_security(
                request_id, user_id, content, metadata
            )
            
            security_context["checks_performed"].append("security_gateway")
            security_context["threat_level"] = threat_level.value
            
            if not is_allowed:
                await self._log_blocked_request(request_id, user_id, reason, threat_level)
                self.metrics["requests_blocked"] += 1
                return False, reason, security_context
        
        # 2. Token Cost Pre-check
        if self.cost_monitor:
            estimated_tokens = await self.cost_monitor.estimate_tokens(content)
            is_allowed, reason, estimated_cost = await self.cost_monitor.pre_request_check(
                user_id, estimated_tokens, 
                model=metadata.get("model", "gpt-4") if metadata else "gpt-4"
            )
            
            security_context["checks_performed"].append("cost_monitor")
            security_context["estimated_cost"] = estimated_cost
            
            if not is_allowed:
                await self._log_blocked_request(request_id, user_id, reason, ThreatLevel.MEDIUM)
                self.metrics["requests_blocked"] += 1
                return False, reason, security_context
        
        # 3. Request Classification
        if self.security_gateway:
            request_type = self.security_gateway.classify_request(content)
            security_context["request_type"] = request_type.value
        
        self.metrics["requests_processed"] += 1
        return True, None, security_context
    
    async def execute_agent_safely(
        self,
        agent_type: str,
        agent_function: Callable,
        args: tuple = (),
        kwargs: dict = None,
        user_id: str = "unknown",
        request_id: Optional[str] = None
    ) -> Tuple[bool, Any, Dict[str, Any]]:
        """
        Execute an agent with full security isolation
        
        Returns:
            Tuple of (success, result, execution_info)
        """
        request_id = request_id or str(uuid.uuid4())
        execution_info = {
            "agent_type": agent_type,
            "request_id": request_id,
            "start_time": datetime.now().isoformat()
        }
        
        try:
            if self.agent_executor:
                # Execute with isolation
                success, result, context = await self.agent_executor.execute_agent(
                    agent_type=agent_type,
                    agent_function=agent_function,
                    args=args,
                    kwargs=kwargs or {},
                    user_id=user_id,
                    request_id=request_id
                )
                
                execution_info["isolation_context"] = {
                    "api_calls_made": context.api_calls_made,
                    "functions_called": context.functions_called,
                    "violations": context.violations
                }
                
                # Log execution
                if self.audit_logger:
                    await self.audit_logger.log_event(AuditEvent(
                        event_type=EventType.AI_REQUEST,
                        severity=Severity.INFO if success else Severity.ERROR,
                        user_id=user_id,
                        request_id=request_id,
                        action=f"Agent {agent_type} execution",
                        outcome="success" if success else "failure",
                        details=execution_info
                    ))
                
                return success, result, execution_info
            else:
                # Direct execution without isolation
                result = await agent_function(*args, **(kwargs or {}))
                return True, result, execution_info
                
        except Exception as e:
            execution_info["error"] = str(e)
            logger.error(f"Agent execution failed: {e}")
            
            if self.audit_logger:
                await self.audit_logger.log_event(AuditEvent(
                    event_type=EventType.AI_ERROR,
                    severity=Severity.ERROR,
                    user_id=user_id,
                    request_id=request_id,
                    action=f"Agent {agent_type} execution failed",
                    error_message=str(e)
                ))
            
            return False, None, execution_info
    
    async def filter_and_validate_response(
        self,
        responses: Dict[str, str],
        content_type: ContentType = ContentType.SUPPLEMENT_RECOMMENDATION,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Filter and validate multi-agent responses
        
        Returns:
            Tuple of (final_response, validation_info)
        """
        validation_info = {
            "filtered": False,
            "validated": False,
            "has_conflicts": False,
            "disclaimers_added": []
        }
        
        # 1. Validate consistency across agents
        if self.response_validator and len(responses) > 1:
            validation_result = await validate_multi_agent_responses(
                responses, self.response_validator
            )
            
            validation_info["validated"] = True
            validation_info["validation_result"] = {
                "is_valid": validation_result.is_valid,
                "confidence_score": validation_result.confidence_score,
                "conflicts": len(validation_result.conflicts),
                "issues": len(validation_result.issues)
            }
            
            if validation_result.conflicts:
                validation_info["has_conflicts"] = True
            
            # Use consensus response if available
            if validation_result.consensus_response:
                final_response = validation_result.consensus_response
            else:
                # Use response from primary agent
                primary_agent = "SupplementSpecialist" if "SupplementSpecialist" in responses else list(responses.keys())[0]
                final_response = responses[primary_agent]
        else:
            # Single response, use as is
            final_response = list(responses.values())[0] if responses else ""
        
        # 2. Apply content filtering
        if self.content_filter:
            filtered_content, violations, metadata = await self.content_filter.filter_content(
                final_response, content_type, user_context
            )
            
            validation_info["filtered"] = metadata["filtered"]
            validation_info["violations"] = len(violations)
            validation_info["disclaimers_added"] = metadata["disclaimers_added"]
            
            final_response = filtered_content
        
        return final_response, validation_info
    
    @asynccontextmanager
    async def track_cost(
        self,
        request_id: str,
        user_id: str,
        model: str,
        agent_type: Optional[str] = None
    ):
        """Context manager for tracking LLM costs"""
        if not self.cost_monitor:
            yield None
            return
        
        tracker = CostTracker(
            cost_monitor=self.cost_monitor,
            request_id=request_id,
            user_id=user_id,
            model=model,
            agent_type=agent_type
        )
        
        async with tracker as t:
            yield t
            
        # Update metrics
        self.metrics["total_cost"] += tracker.input_tokens * 0.00003 + tracker.output_tokens * 0.00006  # Example pricing
    
    async def _log_blocked_request(
        self,
        request_id: str,
        user_id: str,
        reason: str,
        threat_level: ThreatLevel
    ):
        """Log blocked request"""
        if self.audit_logger:
            await self.audit_logger.log_security_event(
                event_type=EventType.SECURITY_ALERT,
                severity=Severity.WARNING if threat_level.value < 3 else Severity.CRITICAL,
                user_id=user_id,
                threat_type="request_blocked",
                details={
                    "request_id": request_id,
                    "reason": reason,
                    "threat_level": threat_level.value
                }
            )
        
        self.metrics["security_events"] += 1
    
    def get_security_metrics(self) -> Dict[str, Any]:
        """Get comprehensive security metrics"""
        metrics = {
            "system": self.metrics.copy(),
            "components": {}
        }
        
        if self.security_gateway:
            metrics["components"]["security_gateway"] = self.security_gateway.get_metrics()
        
        if self.cost_monitor:
            metrics["components"]["cost_monitor"] = self.cost_monitor.get_usage_report("day")
        
        if self.audit_logger:
            metrics["components"]["audit_logger"] = self.audit_logger.get_statistics()
        
        if self.content_filter:
            metrics["components"]["content_filter"] = self.content_filter.get_statistics()
        
        if self.agent_executor:
            metrics["components"]["agent_executor"] = self.agent_executor.get_execution_stats()
        
        if self.response_validator:
            metrics["components"]["response_validator"] = self.response_validator.get_validation_stats()
        
        return metrics
    
    def create_fastapi_middleware(self, app: FastAPI):
        """Create and attach FastAPI middleware"""
        if self.security_gateway:
            app.add_middleware(SecurityMiddleware, security_gateway=self.security_gateway)
            logger.info("Security middleware attached to FastAPI app")
    
    async def generate_security_report(
        self,
        report_type: str = "daily",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive security report"""
        if not start_time:
            start_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if not end_time:
            end_time = datetime.now()
        
        report = {
            "report_type": report_type,
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "generated_at": datetime.now().isoformat(),
            "summary": {},
            "details": {}
        }
        
        # Get metrics
        metrics = self.get_security_metrics()
        report["summary"]["total_requests"] = metrics["system"]["requests_processed"]
        report["summary"]["blocked_requests"] = metrics["system"]["requests_blocked"]
        report["summary"]["total_cost_usd"] = round(metrics["system"]["total_cost"], 2)
        report["summary"]["security_events"] = metrics["system"]["security_events"]
        
        # Get audit events if available
        if self.audit_logger:
            security_events = await self.audit_logger.search_events(
                start_time=start_time,
                end_time=end_time,
                event_types=[EventType.SECURITY_ALERT, EventType.MALICIOUS_REQUEST],
                limit=100
            )
            report["details"]["security_events"] = security_events
        
        return report


# Singleton instance
_security_system: Optional[IntegratedSecuritySystem] = None


def get_security_system(config: Optional[SecurityConfig] = None) -> IntegratedSecuritySystem:
    """Get or create singleton security system instance"""
    global _security_system
    if _security_system is None:
        _security_system = IntegratedSecuritySystem(config)
    return _security_system


# Decorators for easy integration
def secure_endpoint(
    require_auth: bool = True,
    check_rate_limit: bool = True,
    track_cost: bool = True
):
    """Decorator to secure API endpoints"""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            security = get_security_system()
            
            # Extract user info
            user_id = request.headers.get("X-User-ID", "anonymous")
            request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
            
            # Check security if request has body
            if request.method in ["POST", "PUT", "PATCH"]:
                body = await request.body()
                content = body.decode('utf-8') if body else ""
                
                is_allowed, reason, context = await security.process_request(
                    request_id=request_id,
                    user_id=user_id,
                    content=content,
                    metadata={"path": request.url.path, "method": request.method}
                )
                
                if not is_allowed:
                    return Response(
                        content=json.dumps({
                            "error": "Request blocked",
                            "reason": reason,
                            "request_id": request_id
                        }),
                        status_code=403,
                        media_type="application/json"
                    )
            
            # Execute function
            result = await func(request, *args, **kwargs)
            
            return result
        
        return wrapper
    return decorator


def secure_agent(
    agent_type: str,
    track_cost: bool = True,
    validate_response: bool = True
):
    """Decorator to secure agent functions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            security = get_security_system()
            
            # Extract context
            user_id = kwargs.get("user_id", "unknown")
            request_id = kwargs.get("request_id", str(uuid.uuid4()))
            
            # Execute with security
            success, result, info = await security.execute_agent_safely(
                agent_type=agent_type,
                agent_function=func,
                args=args,
                kwargs=kwargs,
                user_id=user_id,
                request_id=request_id
            )
            
            if not success:
                raise Exception(f"Agent execution failed: {info}")
            
            return result
        
        return wrapper
    return decorator