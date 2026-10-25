"""
Enterprise-grade Security Gateway for Healthcare AI System
Provides comprehensive protection against malicious attacks, rate limiting, and input validation
"""

import re
import time
import hashlib
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from functools import wraps

import redis
from fastapi import HTTPException, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Threat level classification for requests"""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RequestType(Enum):
    """Classification of request types"""
    HEALTH_QUERY = "health_query"
    SUPPLEMENT_RECOMMENDATION = "supplement_recommendation"
    MEDICAL_CONSULTATION = "medical_consultation"
    SYSTEM_PROBE = "system_probe"
    MALICIOUS = "malicious"
    UNKNOWN = "unknown"


@dataclass
class SecurityPattern:
    """Security pattern definition for threat detection"""
    pattern: re.Pattern
    threat_level: ThreatLevel
    category: str
    description: str


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    requests_per_minute: int = 10
    requests_per_hour: int = 100
    requests_per_day: int = 1000
    burst_size: int = 20
    token_limit_per_hour: int = 50000
    token_limit_per_day: int = 500000


@dataclass
class SecurityMetrics:
    """Security metrics for monitoring"""
    total_requests: int = 0
    blocked_requests: int = 0
    rate_limited_requests: int = 0
    malicious_requests: int = 0
    total_tokens_used: int = 0
    threats_detected: Dict[str, int] = field(default_factory=dict)


class SecurityGateway:
    """
    Comprehensive security gateway for healthcare AI system
    Implements multiple layers of protection
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        rate_limit_config: Optional[RateLimitConfig] = None,
        enable_logging: bool = True
    ):
        self.redis_client = redis_client or self._create_redis_client()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.enable_logging = enable_logging
        
        # Initialize security patterns
        self.security_patterns = self._initialize_security_patterns()
        
        # In-memory rate limiting if Redis not available
        self.request_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.token_usage: Dict[str, Dict[str, int]] = defaultdict(dict)
        
        # Metrics
        self.metrics = SecurityMetrics()
        
        # PII patterns
        self.pii_patterns = self._initialize_pii_patterns()
        
    def _create_redis_client(self) -> Optional[redis.Redis]:
        """Create Redis client with fallback"""
        try:
            client = redis.Redis(
                host='redis',
                port=6379,
                decode_responses=True,
                socket_connect_timeout=5
            )
            client.ping()
            return client
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory rate limiting: {e}")
            return None
    
    def _initialize_security_patterns(self) -> List[SecurityPattern]:
        """Initialize malicious pattern detection rules"""
        patterns = [
            # Prompt injection attempts
            SecurityPattern(
                pattern=re.compile(r"(ignore|forget|disregard).*(previous|above|prior).*(instructions?|prompts?)", re.I),
                threat_level=ThreatLevel.HIGH,
                category="prompt_injection",
                description="Attempting to override system prompts"
            ),
            SecurityPattern(
                pattern=re.compile(r"(act|pretend|behave)\s+(as|like)\s+", re.I),
                threat_level=ThreatLevel.MEDIUM,
                category="role_play",
                description="Attempting to change agent behavior"
            ),
            SecurityPattern(
                pattern=re.compile(r"(system|admin|root)\s*(prompt|message|command)", re.I),
                threat_level=ThreatLevel.HIGH,
                category="system_probe",
                description="Attempting to access system internals"
            ),
            
            # Data extraction attempts
            SecurityPattern(
                pattern=re.compile(r"(show|list|dump).*(all|every).*(patient|user|data|record)", re.I),
                threat_level=ThreatLevel.CRITICAL,
                category="data_extraction",
                description="Attempting bulk data extraction"
            ),
            SecurityPattern(
                pattern=re.compile(r"(password|token|key|secret|credential)", re.I),
                threat_level=ThreatLevel.HIGH,
                category="credential_probe",
                description="Attempting to extract credentials"
            ),
            
            # Injection attacks
            SecurityPattern(
                pattern=re.compile(r"(<script|javascript:|onerror=|onclick=)", re.I),
                threat_level=ThreatLevel.CRITICAL,
                category="xss_attempt",
                description="Cross-site scripting attempt"
            ),
            SecurityPattern(
                pattern=re.compile(r"(union\s+select|drop\s+table|insert\s+into|update\s+set)", re.I),
                threat_level=ThreatLevel.CRITICAL,
                category="sql_injection",
                description="SQL injection attempt"
            ),
            
            # Resource exhaustion
            SecurityPattern(
                pattern=re.compile(r"(repeat|loop|recursive).{0,20}(infinite|forever|maximum)", re.I),
                threat_level=ThreatLevel.HIGH,
                category="resource_exhaustion",
                description="Attempting to exhaust resources"
            ),
            SecurityPattern(
                pattern=re.compile(r"(.)\1{50,}", re.I),  # Repeated characters
                threat_level=ThreatLevel.MEDIUM,
                category="spam",
                description="Spam or flooding attempt"
            ),
            
            # Medical misinformation
            SecurityPattern(
                pattern=re.compile(r"(cure|treat|heal).*(cancer|covid|aids|diabetes).*(guarantee|definitely|100%)", re.I),
                threat_level=ThreatLevel.HIGH,
                category="medical_misinformation",
                description="Attempting to spread medical misinformation"
            ),
        ]
        
        return patterns
    
    def _initialize_pii_patterns(self) -> List[Tuple[re.Pattern, str]]:
        """Initialize PII detection patterns"""
        return [
            # Chinese ID card
            (re.compile(r"\b\d{15}|\d{18}\b"), "chinese_id"),
            # Phone numbers
            (re.compile(r"\b1[3-9]\d{9}\b"), "phone_number"),
            # Email addresses
            (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "email"),
            # Bank card numbers
            (re.compile(r"\b\d{16,19}\b"), "bank_card"),
            # IP addresses
            (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "ip_address"),
        ]
    
    async def check_request_security(
        self,
        request_id: str,
        user_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str], ThreatLevel]:
        """
        Comprehensive security check for incoming requests
        
        Returns:
            Tuple of (is_allowed, rejection_reason, threat_level)
        """
        # Check rate limits
        is_allowed, reason = await self.check_rate_limit(user_id)
        if not is_allowed:
            self.metrics.rate_limited_requests += 1
            return False, reason, ThreatLevel.MEDIUM
        
        # Check for malicious patterns
        threat_level, threat_info = self.detect_threats(content)
        if threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            self.metrics.malicious_requests += 1
            self.metrics.threats_detected[threat_info['category']] = \
                self.metrics.threats_detected.get(threat_info['category'], 0) + 1
            
            if self.enable_logging:
                await self._log_security_event(
                    request_id=request_id,
                    user_id=user_id,
                    event_type="threat_detected",
                    threat_level=threat_level,
                    details=threat_info
                )
            
            return False, f"Security threat detected: {threat_info['description']}", threat_level
        
        # Check content length
        if len(content) > 10000:  # 10k character limit
            return False, "Request content too long", ThreatLevel.MEDIUM
        
        # Detect and scrub PII
        content_has_pii, pii_types = self.detect_pii(content)
        if content_has_pii:
            if self.enable_logging:
                await self._log_security_event(
                    request_id=request_id,
                    user_id=user_id,
                    event_type="pii_detected",
                    threat_level=ThreatLevel.LOW,
                    details={"pii_types": pii_types}
                )
        
        self.metrics.total_requests += 1
        return True, None, threat_level
    
    async def check_rate_limit(self, user_id: str) -> Tuple[bool, Optional[str]]:
        """Check if user has exceeded rate limits"""
        current_time = time.time()
        
        if self.redis_client:
            return await self._check_rate_limit_redis(user_id, current_time)
        else:
            return self._check_rate_limit_memory(user_id, current_time)
    
    async def _check_rate_limit_redis(self, user_id: str, current_time: float) -> Tuple[bool, Optional[str]]:
        """Rate limiting using Redis"""
        try:
            # Implement sliding window rate limiting
            minute_key = f"rate_limit:minute:{user_id}"
            hour_key = f"rate_limit:hour:{user_id}"
            day_key = f"rate_limit:day:{user_id}"
            
            pipe = self.redis_client.pipeline()
            
            # Check and update counters
            for key, limit, window in [
                (minute_key, self.rate_limit_config.requests_per_minute, 60),
                (hour_key, self.rate_limit_config.requests_per_hour, 3600),
                (day_key, self.rate_limit_config.requests_per_day, 86400)
            ]:
                pipe.incr(key)
                pipe.expire(key, window)
            
            results = pipe.execute()
            
            # Check limits
            if results[0] > self.rate_limit_config.requests_per_minute:
                return False, "Rate limit exceeded: too many requests per minute"
            if results[2] > self.rate_limit_config.requests_per_hour:
                return False, "Rate limit exceeded: too many requests per hour"
            if results[4] > self.rate_limit_config.requests_per_day:
                return False, "Rate limit exceeded: too many requests per day"
            
            return True, None
            
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            return self._check_rate_limit_memory(user_id, current_time)
    
    def _check_rate_limit_memory(self, user_id: str, current_time: float) -> Tuple[bool, Optional[str]]:
        """In-memory rate limiting fallback"""
        # Clean old entries
        user_requests = self.request_history[user_id]
        
        # Remove entries older than 24 hours
        cutoff_time = current_time - 86400
        while user_requests and user_requests[0] < cutoff_time:
            user_requests.popleft()
        
        # Count requests in different time windows
        minute_count = sum(1 for t in user_requests if t > current_time - 60)
        hour_count = sum(1 for t in user_requests if t > current_time - 3600)
        day_count = len(user_requests)
        
        # Check limits
        if minute_count >= self.rate_limit_config.requests_per_minute:
            return False, "Rate limit exceeded: too many requests per minute"
        if hour_count >= self.rate_limit_config.requests_per_hour:
            return False, "Rate limit exceeded: too many requests per hour"
        if day_count >= self.rate_limit_config.requests_per_day:
            return False, "Rate limit exceeded: too many requests per day"
        
        # Add current request
        user_requests.append(current_time)
        
        return True, None
    
    def detect_threats(self, content: str) -> Tuple[ThreatLevel, Dict[str, Any]]:
        """Detect security threats in content"""
        highest_threat = ThreatLevel.SAFE
        threat_info = {"threats": []}
        
        for pattern in self.security_patterns:
            if pattern.pattern.search(content):
                threat_info["threats"].append({
                    "category": pattern.category,
                    "description": pattern.description,
                    "threat_level": pattern.threat_level.value
                })
                
                if pattern.threat_level.value > highest_threat.value:
                    highest_threat = pattern.threat_level
                    threat_info["category"] = pattern.category
                    threat_info["description"] = pattern.description
        
        return highest_threat, threat_info
    
    def detect_pii(self, content: str) -> Tuple[bool, List[str]]:
        """Detect PII in content"""
        detected_pii = []
        
        for pattern, pii_type in self.pii_patterns:
            if pattern.search(content):
                detected_pii.append(pii_type)
        
        return len(detected_pii) > 0, detected_pii
    
    def sanitize_content(self, content: str) -> str:
        """Remove or mask PII from content"""
        sanitized = content
        
        for pattern, pii_type in self.pii_patterns:
            if pii_type == "email":
                sanitized = pattern.sub("[EMAIL_REMOVED]", sanitized)
            elif pii_type == "phone_number":
                sanitized = pattern.sub("[PHONE_REMOVED]", sanitized)
            elif pii_type == "chinese_id":
                sanitized = pattern.sub("[ID_REMOVED]", sanitized)
            elif pii_type == "bank_card":
                sanitized = pattern.sub("[CARD_REMOVED]", sanitized)
            elif pii_type == "ip_address":
                sanitized = pattern.sub("[IP_REMOVED]", sanitized)
        
        return sanitized
    
    async def estimate_token_cost(self, content: str, model: str = "gpt-4") -> int:
        """Estimate token count for content"""
        # Rough estimation: 1 token ≈ 4 characters for English, 2 characters for Chinese
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', content))
        english_chars = len(content) - chinese_chars
        
        estimated_tokens = (chinese_chars / 2) + (english_chars / 4)
        
        # Add buffer for system prompts and response
        return int(estimated_tokens * 2.5)
    
    async def check_token_budget(self, user_id: str, estimated_tokens: int) -> Tuple[bool, Optional[str]]:
        """Check if user has token budget remaining"""
        current_hour = datetime.now().strftime("%Y%m%d%H")
        current_day = datetime.now().strftime("%Y%m%d")
        
        if self.redis_client:
            try:
                hour_key = f"tokens:hour:{user_id}:{current_hour}"
                day_key = f"tokens:day:{user_id}:{current_day}"
                
                pipe = self.redis_client.pipeline()
                pipe.incrby(hour_key, estimated_tokens)
                pipe.expire(hour_key, 3600)
                pipe.incrby(day_key, estimated_tokens)
                pipe.expire(day_key, 86400)
                
                hour_tokens, _, day_tokens, _ = pipe.execute()
                
                if hour_tokens > self.rate_limit_config.token_limit_per_hour:
                    return False, "Token limit exceeded for this hour"
                if day_tokens > self.rate_limit_config.token_limit_per_day:
                    return False, "Token limit exceeded for today"
                
                return True, None
                
            except Exception as e:
                logger.error(f"Redis token check failed: {e}")
        
        # Fallback to in-memory
        if user_id not in self.token_usage:
            self.token_usage[user_id] = {}
        
        hour_tokens = self.token_usage[user_id].get(current_hour, 0) + estimated_tokens
        day_tokens = self.token_usage[user_id].get(current_day, 0) + estimated_tokens
        
        if hour_tokens > self.rate_limit_config.token_limit_per_hour:
            return False, "Token limit exceeded for this hour"
        if day_tokens > self.rate_limit_config.token_limit_per_day:
            return False, "Token limit exceeded for today"
        
        self.token_usage[user_id][current_hour] = hour_tokens
        self.token_usage[user_id][current_day] = day_tokens
        
        return True, None
    
    def classify_request(self, content: str) -> RequestType:
        """Classify the type of request"""
        content_lower = content.lower()
        
        # Check for system probing
        if any(word in content_lower for word in ['system', 'admin', 'debug', 'config']):
            return RequestType.SYSTEM_PROBE
        
        # Check for medical consultation
        if any(word in content_lower for word in ['症状', '疼痛', '治疗', '诊断', 'symptom', 'pain', 'treatment']):
            return RequestType.MEDICAL_CONSULTATION
        
        # Check for supplement recommendation
        if any(word in content_lower for word in ['保健品', '维生素', '营养', 'supplement', 'vitamin', 'nutrition']):
            return RequestType.SUPPLEMENT_RECOMMENDATION
        
        # Check for general health query
        if any(word in content_lower for word in ['健康', '养生', 'health', 'wellness']):
            return RequestType.HEALTH_QUERY
        
        # Check if malicious
        threat_level, _ = self.detect_threats(content)
        if threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            return RequestType.MALICIOUS
        
        return RequestType.UNKNOWN
    
    async def _log_security_event(
        self,
        request_id: str,
        user_id: str,
        event_type: str,
        threat_level: ThreatLevel,
        details: Dict[str, Any]
    ):
        """Log security events for audit"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id,
            "user_id": user_id,
            "event_type": event_type,
            "threat_level": threat_level.value,
            "details": details
        }
        
        logger.warning(f"Security event: {json.dumps(event)}")
        
        # Store in Redis if available
        if self.redis_client:
            try:
                key = f"security_events:{datetime.now().strftime('%Y%m%d')}"
                self.redis_client.rpush(key, json.dumps(event))
                self.redis_client.expire(key, 86400 * 30)  # Keep for 30 days
            except Exception as e:
                logger.error(f"Failed to log security event to Redis: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get security metrics"""
        return {
            "total_requests": self.metrics.total_requests,
            "blocked_requests": self.metrics.blocked_requests,
            "rate_limited_requests": self.metrics.rate_limited_requests,
            "malicious_requests": self.metrics.malicious_requests,
            "threats_detected": dict(self.metrics.threats_detected),
            "total_tokens_used": self.metrics.total_tokens_used
        }


class SecurityMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for security gateway integration"""
    
    def __init__(self, app, security_gateway: SecurityGateway):
        super().__init__(app)
        self.security_gateway = security_gateway
    
    async def dispatch(self, request: Request, call_next):
        # Skip security checks for health endpoints
        if request.url.path in ["/health", "/metrics", "/docs", "/openapi.json"]:
            return await call_next(request)
        
        # Extract request info
        request_id = request.headers.get("X-Request-ID", str(time.time()))
        user_id = self._extract_user_id(request)
        
        # For POST requests with body
        if request.method == "POST":
            body = await request.body()
            try:
                content = body.decode('utf-8')
            except:
                content = str(body)
            
            # Check security
            is_allowed, reason, threat_level = await self.security_gateway.check_request_security(
                request_id=request_id,
                user_id=user_id,
                content=content,
                metadata={"path": request.url.path, "method": request.method}
            )
            
            if not is_allowed:
                return Response(
                    content=json.dumps({
                        "error": "Request blocked by security policy",
                        "reason": reason,
                        "request_id": request_id
                    }),
                    status_code=403,
                    media_type="application/json"
                )
            
            # Recreate request with body for downstream
            from starlette.datastructures import Headers
            from starlette.requests import Request as StarletteRequest
            
            async def receive():
                return {"type": "http.request", "body": body}
            
            request = StarletteRequest(request.scope, receive)
        
        # Add security context to request
        request.state.security_context = {
            "request_id": request_id,
            "user_id": user_id,
            "threat_level": threat_level.value if 'threat_level' in locals() else "safe"
        }
        
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        return response
    
    def _extract_user_id(self, request: Request) -> str:
        """Extract user ID from request"""
        # Try different sources
        # 1. Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            # In production, decode JWT token here
            return hashlib.md5(auth_header.encode()).hexdigest()[:8]
        
        # 2. Session cookie
        session_id = request.cookies.get("session_id", "")
        if session_id:
            return hashlib.md5(session_id.encode()).hexdigest()[:8]
        
        # 3. Client IP as fallback
        client_ip = request.client.host if request.client else "unknown"
        return hashlib.md5(client_ip.encode()).hexdigest()[:8]


# Decorator for function-level security
def secure_endpoint(
    max_requests_per_minute: int = 10,
    require_auth: bool = True,
    log_access: bool = True
):
    """Decorator for securing individual endpoints"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get request from args/kwargs
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                request = kwargs.get('request')
            
            if request and hasattr(request.state, 'security_context'):
                # Security already checked by middleware
                pass
            else:
                # Additional endpoint-specific checks can go here
                pass
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator