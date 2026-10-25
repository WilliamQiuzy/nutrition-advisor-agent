"""
Enterprise-grade Audit Logging System for Healthcare AI
Provides comprehensive, compliant, and searchable audit trails
"""

import json
import logging
import time
import hashlib
import uuid
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
import asyncio
import gzip
import os

import redis
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EventType(Enum):
    """Types of auditable events"""
    # Authentication & Authorization
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    AUTH_FAILURE = "auth_failure"
    PERMISSION_DENIED = "permission_denied"
    
    # Data Access
    PATIENT_DATA_ACCESS = "patient_data_access"
    PATIENT_DATA_MODIFICATION = "patient_data_modification"
    PHI_EXPORT = "phi_export"
    
    # AI Operations
    AI_REQUEST = "ai_request"
    AI_RESPONSE = "ai_response"
    AI_ERROR = "ai_error"
    AGENT_DECISION = "agent_decision"
    
    # Security Events
    SECURITY_ALERT = "security_alert"
    MALICIOUS_REQUEST = "malicious_request"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    
    # System Events
    CONFIG_CHANGE = "config_change"
    SYSTEM_ERROR = "system_error"
    MAINTENANCE = "maintenance"
    
    # Compliance
    CONSENT_GRANTED = "consent_granted"
    CONSENT_REVOKED = "consent_revoked"
    DATA_RETENTION = "data_retention"


class Severity(Enum):
    """Event severity levels"""
    DEBUG = 1
    INFO = 2
    WARNING = 3
    ERROR = 4
    CRITICAL = 5


@dataclass
class AuditEvent:
    """Comprehensive audit event structure"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    event_type: EventType = EventType.AI_REQUEST
    severity: Severity = Severity.INFO
    
    # User context
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Request context
    request_id: Optional[str] = None
    endpoint: Optional[str] = None
    http_method: Optional[str] = None
    
    # Data context
    resource_type: Optional[str] = None  # e.g., "patient", "supplement", "recommendation"
    resource_id: Optional[str] = None
    patient_id: Optional[str] = None  # Separate field for HIPAA compliance
    
    # Event details
    action: str = ""  # What was done
    outcome: str = "success"  # success, failure, partial
    details: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    
    # Security context
    risk_score: Optional[float] = None
    threat_indicators: List[str] = field(default_factory=list)
    
    # Compliance metadata
    data_classification: str = "internal"  # public, internal, confidential, restricted
    retention_days: int = 2555  # 7 years default for HIPAA
    requires_encryption: bool = True
    
    # System context
    service_name: str = "healthcare-ai"
    service_version: Optional[str] = None
    environment: str = "production"
    host: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with proper serialization"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['event_type'] = self.event_type.value
        data['severity'] = self.severity.value
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


class AuditLogger:
    """
    Comprehensive audit logging system with encryption, compression, and search capabilities
    Compliant with HIPAA, GDPR, and other healthcare regulations
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        log_dir: str = "/var/log/healthcare-ai/audit",
        encryption_key: Optional[str] = None,
        enable_compression: bool = True,
        enable_redis: bool = True,
        retention_policies: Optional[Dict[str, int]] = None
    ):
        self.redis_client = redis_client or self._create_redis_client() if enable_redis else None
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Encryption setup
        self.encryption_key = encryption_key or os.environ.get("AUDIT_ENCRYPTION_KEY")
        self.cipher = self._setup_encryption()
        
        self.enable_compression = enable_compression
        
        # Retention policies (days)
        self.retention_policies = retention_policies or {
            "patient_data_access": 2555,  # 7 years
            "patient_data_modification": 2555,
            "phi_export": 2555,
            "ai_request": 365,  # 1 year
            "security_alert": 1095,  # 3 years
            "system_error": 90,
            "default": 365
        }
        
        # In-memory buffer for performance
        self.event_buffer: List[AuditEvent] = []
        self.buffer_size = 100
        self.last_flush = time.time()
        
        # Statistics
        self.stats = {
            "total_events": 0,
            "events_by_type": {},
            "events_by_severity": {}
        }
    
    def _create_redis_client(self) -> Optional[redis.Redis]:
        """Create Redis client with fallback"""
        try:
            client = redis.Redis(
                host='redis',
                port=6379,
                decode_responses=False,  # We'll handle encoding for encryption
                socket_connect_timeout=5
            )
            client.ping()
            return client
        except Exception as e:
            logger.warning(f"Redis connection failed for audit logging: {e}")
            return None
    
    def _setup_encryption(self) -> Optional[Fernet]:
        """Setup encryption for sensitive audit logs"""
        if not self.encryption_key:
            # Generate a key if none provided (should be stored securely)
            self.encryption_key = Fernet.generate_key().decode()
            logger.warning("Generated new encryption key for audit logs. Store this securely!")
        
        try:
            return Fernet(self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key)
        except Exception as e:
            logger.error(f"Failed to setup encryption: {e}")
            return None
    
    async def log_event(self, event: AuditEvent) -> str:
        """Log an audit event"""
        # Update statistics
        self.stats["total_events"] += 1
        self.stats["events_by_type"][event.event_type.value] = \
            self.stats["events_by_type"].get(event.event_type.value, 0) + 1
        self.stats["events_by_severity"][event.severity.value] = \
            self.stats["events_by_severity"].get(event.severity.value, 0) + 1
        
        # Add to buffer
        self.event_buffer.append(event)
        
        # Check if we should flush
        if len(self.event_buffer) >= self.buffer_size or \
           time.time() - self.last_flush > 60:  # Flush every minute
            await self._flush_buffer()
        
        # Log critical events immediately
        if event.severity == Severity.CRITICAL:
            await self._write_event(event)
            logger.critical(f"Critical audit event: {event.event_type.value} - {event.action}")
        
        return event.event_id
    
    async def _flush_buffer(self):
        """Flush event buffer to storage"""
        if not self.event_buffer:
            return
        
        events_to_write = self.event_buffer[:]
        self.event_buffer.clear()
        self.last_flush = time.time()
        
        # Write to file
        for event in events_to_write:
            await self._write_event(event)
        
        # Batch write to Redis if available
        if self.redis_client:
            await self._batch_write_redis(events_to_write)
    
    async def _write_event(self, event: AuditEvent):
        """Write single event to file"""
        # Determine file path
        date_str = event.timestamp.strftime("%Y%m%d")
        hour_str = event.timestamp.strftime("%H")
        
        file_path = self.log_dir / f"audit_{date_str}_{hour_str}.log"
        if self.enable_compression:
            file_path = file_path.with_suffix(".log.gz")
        
        # Prepare event data
        event_json = event.to_json()
        
        # Encrypt if needed
        if event.requires_encryption and self.cipher:
            event_data = self.cipher.encrypt(event_json.encode()).decode()
        else:
            event_data = event_json
        
        # Write to file
        try:
            if self.enable_compression:
                with gzip.open(file_path, 'at', encoding='utf-8') as f:
                    f.write(event_data + '\n')
            else:
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(event_data + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit event to file: {e}")
    
    async def _batch_write_redis(self, events: List[AuditEvent]):
        """Batch write events to Redis"""
        if not self.redis_client:
            return
        
        try:
            pipe = self.redis_client.pipeline()
            
            for event in events:
                # Store in multiple indexes for efficient querying
                event_key = f"audit:event:{event.event_id}"
                event_data = event.to_json()
                
                # Encrypt if needed
                if event.requires_encryption and self.cipher:
                    event_data = self.cipher.encrypt(event_data.encode())
                
                # Main event storage
                pipe.setex(
                    event_key,
                    self.retention_policies.get(event.event_type.value, self.retention_policies["default"]) * 86400,
                    event_data
                )
                
                # Time-based index
                time_key = f"audit:time:{event.timestamp.strftime('%Y%m%d')}:{event.event_type.value}"
                pipe.zadd(time_key, {event.event_id: event.timestamp.timestamp()})
                pipe.expire(time_key, 86400 * 90)  # Keep index for 90 days
                
                # User index
                if event.user_id:
                    user_key = f"audit:user:{event.user_id}:{event.timestamp.strftime('%Y%m')}"
                    pipe.zadd(user_key, {event.event_id: event.timestamp.timestamp()})
                    pipe.expire(user_key, 86400 * 90)
                
                # Patient index (for HIPAA compliance)
                if event.patient_id:
                    patient_key = f"audit:patient:{event.patient_id}"
                    pipe.zadd(patient_key, {event.event_id: event.timestamp.timestamp()})
                    pipe.expire(patient_key, 86400 * 2555)  # 7 years
            
            pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to write audit events to Redis: {e}")
    
    async def log_login(self, user_id: str, success: bool, ip_address: str, details: Optional[Dict] = None):
        """Log user login attempt"""
        event = AuditEvent(
            event_type=EventType.USER_LOGIN if success else EventType.AUTH_FAILURE,
            severity=Severity.INFO if success else Severity.WARNING,
            user_id=user_id,
            ip_address=ip_address,
            action=f"User {'logged in' if success else 'failed to log in'}",
            outcome="success" if success else "failure",
            details=details or {}
        )
        return await self.log_event(event)
    
    async def log_data_access(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        patient_id: Optional[str] = None,
        details: Optional[Dict] = None
    ):
        """Log data access event"""
        event = AuditEvent(
            event_type=EventType.PATIENT_DATA_ACCESS,
            severity=Severity.INFO,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            patient_id=patient_id,
            action=action,
            details=details or {},
            data_classification="confidential" if patient_id else "internal"
        )
        return await self.log_event(event)
    
    async def log_ai_request(
        self,
        request_id: str,
        user_id: str,
        agent_type: str,
        input_tokens: int,
        output_tokens: int,
        cost: float,
        success: bool,
        details: Optional[Dict] = None
    ):
        """Log AI request and response"""
        event = AuditEvent(
            event_type=EventType.AI_REQUEST,
            severity=Severity.INFO if success else Severity.ERROR,
            request_id=request_id,
            user_id=user_id,
            action=f"AI request to {agent_type}",
            outcome="success" if success else "failure",
            details={
                "agent_type": agent_type,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "cost_usd": cost,
                **(details or {})
            }
        )
        return await self.log_event(event)
    
    async def log_security_event(
        self,
        event_type: EventType,
        severity: Severity,
        user_id: Optional[str],
        threat_type: str,
        details: Dict[str, Any]
    ):
        """Log security-related event"""
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            action=f"Security event: {threat_type}",
            threat_indicators=[threat_type],
            risk_score=details.get("risk_score", 0.5),
            details=details
        )
        return await self.log_event(event)
    
    async def search_events(
        self,
        start_time: datetime,
        end_time: datetime,
        event_types: Optional[List[EventType]] = None,
        user_id: Optional[str] = None,
        patient_id: Optional[str] = None,
        severity_min: Optional[Severity] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search audit events with filters"""
        events = []
        
        # Search in Redis if available
        if self.redis_client:
            events.extend(await self._search_redis(
                start_time, end_time, event_types, user_id, patient_id, severity_min, limit
            ))
        
        # If not enough results, search files
        if len(events) < limit:
            events.extend(await self._search_files(
                start_time, end_time, event_types, user_id, patient_id, severity_min, limit - len(events)
            ))
        
        return events
    
    async def _search_redis(
        self,
        start_time: datetime,
        end_time: datetime,
        event_types: Optional[List[EventType]],
        user_id: Optional[str],
        patient_id: Optional[str],
        severity_min: Optional[Severity],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Search events in Redis"""
        if not self.redis_client:
            return []
        
        events = []
        
        try:
            # Use appropriate index based on search criteria
            if patient_id:
                # Use patient index for HIPAA compliance
                key = f"audit:patient:{patient_id}"
                event_ids = self.redis_client.zrangebyscore(
                    key,
                    start_time.timestamp(),
                    end_time.timestamp(),
                    start=0,
                    num=limit
                )
            elif user_id:
                # Use user index
                results = []
                current = start_time
                while current <= end_time and len(results) < limit:
                    key = f"audit:user:{user_id}:{current.strftime('%Y%m')}"
                    month_events = self.redis_client.zrangebyscore(
                        key,
                        max(start_time.timestamp(), current.timestamp()),
                        min(end_time.timestamp(), (current + timedelta(days=31)).timestamp())
                    )
                    results.extend(month_events)
                    current += timedelta(days=31)
                event_ids = results[:limit]
            else:
                # Use time-based index
                event_ids = []
                current = start_time.date()
                while current <= end_time.date() and len(event_ids) < limit:
                    for event_type in (event_types or [e for e in EventType]):
                        key = f"audit:time:{current.strftime('%Y%m%d')}:{event_type.value}"
                        day_events = self.redis_client.zrangebyscore(
                            key,
                            max(start_time.timestamp(), datetime.combine(current, datetime.min.time()).timestamp()),
                            min(end_time.timestamp(), datetime.combine(current, datetime.max.time()).timestamp())
                        )
                        event_ids.extend(day_events)
                    current += timedelta(days=1)
            
            # Retrieve actual events
            for event_id in event_ids[:limit]:
                event_data = self.redis_client.get(f"audit:event:{event_id}")
                if event_data:
                    # Decrypt if needed
                    if self.cipher:
                        try:
                            event_data = self.cipher.decrypt(event_data).decode()
                        except:
                            event_data = event_data.decode() if isinstance(event_data, bytes) else event_data
                    else:
                        event_data = event_data.decode() if isinstance(event_data, bytes) else event_data
                    
                    event = json.loads(event_data)
                    
                    # Apply filters
                    if severity_min and event.get("severity", 0) < severity_min.value:
                        continue
                    
                    events.append(event)
            
        except Exception as e:
            logger.error(f"Failed to search events in Redis: {e}")
        
        return events
    
    async def _search_files(
        self,
        start_time: datetime,
        end_time: datetime,
        event_types: Optional[List[EventType]],
        user_id: Optional[str],
        patient_id: Optional[str],
        severity_min: Optional[Severity],
        limit: int
    ) -> List[Dict[str, Any]]:
        """Search events in log files"""
        events = []
        
        # Generate list of files to search
        current = start_time
        while current <= end_time and len(events) < limit:
            date_str = current.strftime("%Y%m%d")
            hour_str = current.strftime("%H")
            
            file_pattern = f"audit_{date_str}_{hour_str}.log*"
            for file_path in self.log_dir.glob(file_pattern):
                if len(events) >= limit:
                    break
                
                try:
                    if file_path.suffix == '.gz':
                        open_func = gzip.open
                    else:
                        open_func = open
                    
                    with open_func(file_path, 'rt', encoding='utf-8') as f:
                        for line in f:
                            if len(events) >= limit:
                                break
                            
                            line = line.strip()
                            if not line:
                                continue
                            
                            # Decrypt if needed
                            if self.cipher:
                                try:
                                    line = self.cipher.decrypt(line.encode()).decode()
                                except:
                                    pass
                            
                            try:
                                event = json.loads(line)
                                
                                # Apply filters
                                event_time = datetime.fromisoformat(event["timestamp"])
                                if event_time < start_time or event_time > end_time:
                                    continue
                                
                                if event_types and event["event_type"] not in [et.value for et in event_types]:
                                    continue
                                
                                if user_id and event.get("user_id") != user_id:
                                    continue
                                
                                if patient_id and event.get("patient_id") != patient_id:
                                    continue
                                
                                if severity_min and event.get("severity", 0) < severity_min.value:
                                    continue
                                
                                events.append(event)
                                
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse audit log line: {line[:100]}...")
                
                except Exception as e:
                    logger.error(f"Failed to read audit file {file_path}: {e}")
            
            current += timedelta(hours=1)
        
        return events
    
    async def generate_compliance_report(
        self,
        report_type: str,
        start_time: datetime,
        end_time: datetime,
        output_format: str = "json"
    ) -> Union[Dict[str, Any], str]:
        """Generate compliance reports for auditors"""
        report_data = {
            "report_type": report_type,
            "generated_at": datetime.now().isoformat(),
            "period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "summary": {},
            "details": []
        }
        
        if report_type == "hipaa_access":
            # HIPAA access report
            access_events = await self.search_events(
                start_time, end_time,
                event_types=[EventType.PATIENT_DATA_ACCESS, EventType.PATIENT_DATA_MODIFICATION, EventType.PHI_EXPORT]
            )
            
            report_data["summary"] = {
                "total_access_events": len(access_events),
                "unique_users": len(set(e.get("user_id") for e in access_events if e.get("user_id"))),
                "unique_patients": len(set(e.get("patient_id") for e in access_events if e.get("patient_id"))),
                "data_exports": sum(1 for e in access_events if e.get("event_type") == EventType.PHI_EXPORT.value)
            }
            
            report_data["details"] = access_events
            
        elif report_type == "security":
            # Security report
            security_events = await self.search_events(
                start_time, end_time,
                event_types=[EventType.SECURITY_ALERT, EventType.MALICIOUS_REQUEST, EventType.AUTH_FAILURE]
            )
            
            report_data["summary"] = {
                "total_security_events": len(security_events),
                "critical_events": sum(1 for e in security_events if e.get("severity") == Severity.CRITICAL.value),
                "unique_threat_types": len(set(
                    threat for e in security_events
                    for threat in e.get("threat_indicators", [])
                ))
            }
            
            report_data["details"] = security_events
            
        elif report_type == "user_activity":
            # User activity report
            all_events = await self.search_events(start_time, end_time)
            
            user_stats = {}
            for event in all_events:
                user_id = event.get("user_id")
                if user_id:
                    if user_id not in user_stats:
                        user_stats[user_id] = {
                            "total_events": 0,
                            "event_types": {},
                            "last_activity": None
                        }
                    
                    user_stats[user_id]["total_events"] += 1
                    event_type = event.get("event_type", "unknown")
                    user_stats[user_id]["event_types"][event_type] = \
                        user_stats[user_id]["event_types"].get(event_type, 0) + 1
                    
                    event_time = event.get("timestamp")
                    if event_time and (not user_stats[user_id]["last_activity"] or 
                                      event_time > user_stats[user_id]["last_activity"]):
                        user_stats[user_id]["last_activity"] = event_time
            
            report_data["summary"] = {
                "total_users": len(user_stats),
                "total_events": sum(u["total_events"] for u in user_stats.values()),
                "most_active_users": sorted(
                    [(uid, stats["total_events"]) for uid, stats in user_stats.items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:10]
            }
            
            report_data["details"] = user_stats
        
        if output_format == "json":
            return report_data
        else:
            # Convert to other formats as needed
            return json.dumps(report_data, indent=2)
    
    async def cleanup_old_logs(self):
        """Clean up old log files based on retention policies"""
        current_time = datetime.now()
        
        for file_path in self.log_dir.glob("audit_*.log*"):
            try:
                # Extract date from filename
                filename = file_path.stem.split('.')[0]  # Remove .log.gz extension
                date_str = filename.split('_')[1]  # audit_YYYYMMDD_HH
                file_date = datetime.strptime(date_str, "%Y%m%d")
                
                # Determine retention period based on content
                # This is simplified - in production, you'd parse the file to check event types
                retention_days = self.retention_policies["default"]
                
                if (current_time - file_date).days > retention_days:
                    file_path.unlink()
                    logger.info(f"Deleted old audit log: {file_path}")
                    
            except Exception as e:
                logger.error(f"Failed to process file {file_path} for cleanup: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get audit system statistics"""
        return {
            "total_events_logged": self.stats["total_events"],
            "events_by_type": dict(self.stats["events_by_type"]),
            "events_by_severity": dict(self.stats["events_by_severity"]),
            "buffer_size": len(self.event_buffer),
            "redis_connected": self.redis_client is not None,
            "encryption_enabled": self.cipher is not None
        }


# Singleton instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get or create singleton audit logger instance"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


# Decorators for easy audit logging
def audit_access(resource_type: str):
    """Decorator to audit data access"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            audit = get_audit_logger()
            
            # Extract context (would need to be adapted based on your framework)
            user_id = kwargs.get("user_id") or "unknown"
            resource_id = kwargs.get("resource_id") or kwargs.get("id") or "unknown"
            
            # Log access
            await audit.log_data_access(
                user_id=user_id,
                resource_type=resource_type,
                resource_id=str(resource_id),
                action=f"Accessed {resource_type} via {func.__name__}"
            )
            
            # Execute function
            result = await func(*args, **kwargs)
            
            return result
        
        return wrapper
    return decorator


def audit_modification(resource_type: str):
    """Decorator to audit data modifications"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            audit = get_audit_logger()
            
            # Extract context
            user_id = kwargs.get("user_id") or "unknown"
            resource_id = kwargs.get("resource_id") or kwargs.get("id") or "unknown"
            
            # Log modification
            event = AuditEvent(
                event_type=EventType.PATIENT_DATA_MODIFICATION,
                severity=Severity.INFO,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=str(resource_id),
                action=f"Modified {resource_type} via {func.__name__}",
                details={"function": func.__name__, "args": str(args)[:200]}
            )
            
            await audit.log_event(event)
            
            # Execute function
            result = await func(*args, **kwargs)
            
            return result
        
        return wrapper
    return decorator