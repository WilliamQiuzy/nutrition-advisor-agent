"""
Enterprise-grade Cost Monitoring System for LLM Token Usage
Tracks, monitors, and controls AI model usage costs with real-time alerts
"""

import json
import logging
import time
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import asyncio
from functools import lru_cache

import redis
import tiktoken
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelProvider(Enum):
    """Supported LLM providers"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    CUSTOM = "custom"


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ModelPricing:
    """Pricing information for different models"""
    provider: ModelProvider
    model_name: str
    input_price_per_1k: float  # USD per 1000 tokens
    output_price_per_1k: float  # USD per 1000 tokens
    context_window: int
    
    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD"""
        input_cost = (input_tokens / 1000) * self.input_price_per_1k
        output_cost = (output_tokens / 1000) * self.output_price_per_1k
        return round(input_cost + output_cost, 6)


@dataclass
class TokenUsage:
    """Token usage tracking"""
    request_id: str
    user_id: str
    timestamp: datetime
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    agent_type: Optional[str] = None
    request_type: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


@dataclass
class CostAlert:
    """Cost alert configuration"""
    alert_id: str
    name: str
    level: AlertLevel
    threshold_type: str  # "hourly", "daily", "monthly", "per_user", "per_request"
    threshold_value: float  # USD
    notification_channels: List[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class UsageMetrics:
    """Aggregated usage metrics"""
    total_requests: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    successful_requests: int = 0
    failed_requests: int = 0
    by_model: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_user: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    by_agent: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class CostMonitor:
    """
    Comprehensive cost monitoring system for LLM usage
    Provides real-time tracking, budgeting, and alerting
    """
    
    # Default model pricing (as of 2024)
    DEFAULT_PRICING = {
        "gpt-4": ModelPricing(
            provider=ModelProvider.OPENAI,
            model_name="gpt-4",
            input_price_per_1k=0.03,
            output_price_per_1k=0.06,
            context_window=8192
        ),
        "gpt-4-turbo": ModelPricing(
            provider=ModelProvider.OPENAI,
            model_name="gpt-4-turbo",
            input_price_per_1k=0.01,
            output_price_per_1k=0.03,
            context_window=128000
        ),
        "gpt-3.5-turbo": ModelPricing(
            provider=ModelProvider.OPENAI,
            model_name="gpt-3.5-turbo",
            input_price_per_1k=0.0005,
            output_price_per_1k=0.0015,
            context_window=16385
        ),
        "claude-3-opus": ModelPricing(
            provider=ModelProvider.ANTHROPIC,
            model_name="claude-3-opus",
            input_price_per_1k=0.015,
            output_price_per_1k=0.075,
            context_window=200000
        ),
        "claude-3-sonnet": ModelPricing(
            provider=ModelProvider.ANTHROPIC,
            model_name="claude-3-sonnet",
            input_price_per_1k=0.003,
            output_price_per_1k=0.015,
            context_window=200000
        )
    }
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        pricing_config: Optional[Dict[str, ModelPricing]] = None,
        alerts_config: Optional[List[CostAlert]] = None,
        enable_persistence: bool = True
    ):
        self.redis_client = redis_client or self._create_redis_client()
        self.pricing = pricing_config or self.DEFAULT_PRICING.copy()
        self.alerts = {alert.alert_id: alert for alert in (alerts_config or self._default_alerts())}
        self.enable_persistence = enable_persistence
        
        # Token encoders cache
        self._encoders = {}
        
        # In-memory metrics if Redis unavailable
        self.usage_history: List[TokenUsage] = []
        self.hourly_metrics: Dict[str, UsageMetrics] = defaultdict(UsageMetrics)
        self.daily_metrics: Dict[str, UsageMetrics] = defaultdict(UsageMetrics)
        
        # Alert tracking
        self.triggered_alerts: Dict[str, datetime] = {}
        
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
            logger.warning(f"Redis connection failed, using in-memory cost tracking: {e}")
            return None
    
    def _default_alerts(self) -> List[CostAlert]:
        """Default alert configurations"""
        return [
            CostAlert(
                alert_id="hourly_limit",
                name="Hourly Cost Limit",
                level=AlertLevel.WARNING,
                threshold_type="hourly",
                threshold_value=10.0,  # $10/hour
                notification_channels=["log", "webhook"]
            ),
            CostAlert(
                alert_id="daily_limit",
                name="Daily Cost Limit",
                level=AlertLevel.CRITICAL,
                threshold_type="daily",
                threshold_value=100.0,  # $100/day
                notification_channels=["log", "webhook", "email"]
            ),
            CostAlert(
                alert_id="user_hourly_limit",
                name="Per-User Hourly Limit",
                level=AlertLevel.WARNING,
                threshold_type="per_user_hourly",
                threshold_value=5.0,  # $5/hour per user
                notification_channels=["log"]
            ),
            CostAlert(
                alert_id="spike_detection",
                name="Cost Spike Detection",
                level=AlertLevel.WARNING,
                threshold_type="spike",
                threshold_value=3.0,  # 3x normal usage
                notification_channels=["log", "webhook"]
            )
        ]
    
    @lru_cache(maxsize=10)
    def _get_encoder(self, model: str):
        """Get cached token encoder for model"""
        if model not in self._encoders:
            try:
                # Try to get specific encoding for model
                if "gpt-4" in model:
                    self._encoders[model] = tiktoken.encoding_for_model("gpt-4")
                elif "gpt-3.5" in model:
                    self._encoders[model] = tiktoken.encoding_for_model("gpt-3.5-turbo")
                else:
                    # Default to cl100k_base encoding
                    self._encoders[model] = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                logger.warning(f"Failed to get encoder for {model}: {e}")
                self._encoders[model] = tiktoken.get_encoding("cl100k_base")
        
        return self._encoders[model]
    
    async def estimate_tokens(self, text: str, model: str = "gpt-4") -> int:
        """Estimate token count for text"""
        try:
            encoder = self._get_encoder(model)
            return len(encoder.encode(text))
        except Exception as e:
            logger.error(f"Token estimation failed: {e}")
            # Fallback estimation
            return len(text) // 4
    
    async def pre_request_check(
        self,
        user_id: str,
        estimated_input_tokens: int,
        model: str,
        agent_type: Optional[str] = None
    ) -> Tuple[bool, Optional[str], float]:
        """
        Check if request should be allowed based on cost constraints
        
        Returns:
            Tuple of (is_allowed, rejection_reason, estimated_cost)
        """
        # Get pricing
        pricing = self.pricing.get(model)
        if not pricing:
            return False, f"Unknown model: {model}", 0.0
        
        # Estimate cost (assume output ≈ 2x input for response)
        estimated_output_tokens = estimated_input_tokens * 2
        estimated_cost = pricing.calculate_cost(estimated_input_tokens, estimated_output_tokens)
        
        # Check user budget
        user_hourly_cost = await self.get_user_cost(user_id, "hour")
        user_daily_cost = await self.get_user_cost(user_id, "day")
        
        # Check against user limits
        user_hourly_limit = self.alerts.get("user_hourly_limit")
        if user_hourly_limit and user_hourly_limit.enabled:
            if user_hourly_cost + estimated_cost > user_hourly_limit.threshold_value:
                return False, f"User hourly cost limit would be exceeded (${user_hourly_cost:.2f} + ${estimated_cost:.2f} > ${user_hourly_limit.threshold_value})", estimated_cost
        
        # Check system limits
        system_hourly_cost = await self.get_total_cost("hour")
        system_daily_cost = await self.get_total_cost("day")
        
        hourly_alert = self.alerts.get("hourly_limit")
        if hourly_alert and hourly_alert.enabled:
            if system_hourly_cost + estimated_cost > hourly_alert.threshold_value:
                return False, f"System hourly cost limit would be exceeded", estimated_cost
        
        daily_alert = self.alerts.get("daily_limit")
        if daily_alert and daily_alert.enabled:
            if system_daily_cost + estimated_cost > daily_alert.threshold_value:
                return False, f"System daily cost limit would be exceeded", estimated_cost
        
        return True, None, estimated_cost
    
    async def track_usage(
        self,
        request_id: str,
        user_id: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent_type: Optional[str] = None,
        request_type: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> TokenUsage:
        """Track token usage for a request"""
        # Calculate cost
        pricing = self.pricing.get(model, self.DEFAULT_PRICING.get("gpt-4"))
        cost_usd = pricing.calculate_cost(input_tokens, output_tokens)
        
        # Create usage record
        usage = TokenUsage(
            request_id=request_id,
            user_id=user_id,
            timestamp=datetime.now(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost_usd,
            agent_type=agent_type,
            request_type=request_type,
            success=success,
            error_message=error_message
        )
        
        # Store usage
        await self._store_usage(usage)
        
        # Update metrics
        await self._update_metrics(usage)
        
        # Check alerts
        await self._check_alerts(usage)
        
        return usage
    
    async def _store_usage(self, usage: TokenUsage):
        """Store usage data"""
        if self.redis_client and self.enable_persistence:
            try:
                # Store in time-series format
                key = f"usage:{usage.timestamp.strftime('%Y%m%d')}:{usage.user_id}"
                self.redis_client.zadd(
                    key,
                    {json.dumps(usage.__dict__, default=str): usage.timestamp.timestamp()}
                )
                self.redis_client.expire(key, 86400 * 90)  # Keep for 90 days
                
                # Update aggregated metrics
                hour_key = f"metrics:hour:{usage.timestamp.strftime('%Y%m%d%H')}"
                day_key = f"metrics:day:{usage.timestamp.strftime('%Y%m%d')}"
                
                for key in [hour_key, day_key]:
                    pipe = self.redis_client.pipeline()
                    pipe.hincrby(key, "total_requests", 1)
                    pipe.hincrby(key, "total_tokens", usage.total_tokens)
                    pipe.hincrbyfloat(key, "total_cost", usage.cost_usd)
                    pipe.hincrby(key, f"model:{usage.model}:tokens", usage.total_tokens)
                    pipe.hincrbyfloat(key, f"model:{usage.model}:cost", usage.cost_usd)
                    pipe.hincrby(key, f"user:{usage.user_id}:tokens", usage.total_tokens)
                    pipe.hincrbyfloat(key, f"user:{usage.user_id}:cost", usage.cost_usd)
                    if usage.agent_type:
                        pipe.hincrby(key, f"agent:{usage.agent_type}:tokens", usage.total_tokens)
                        pipe.hincrbyfloat(key, f"agent:{usage.agent_type}:cost", usage.cost_usd)
                    pipe.execute()
                
            except Exception as e:
                logger.error(f"Failed to store usage in Redis: {e}")
        
        # Always store in memory as fallback
        self.usage_history.append(usage)
        if len(self.usage_history) > 10000:  # Limit memory usage
            self.usage_history = self.usage_history[-5000:]
    
    async def _update_metrics(self, usage: TokenUsage):
        """Update aggregated metrics"""
        hour_key = usage.timestamp.strftime('%Y%m%d%H')
        day_key = usage.timestamp.strftime('%Y%m%d')
        
        # Update hourly metrics
        hourly = self.hourly_metrics[hour_key]
        hourly.total_requests += 1
        hourly.total_tokens += usage.total_tokens
        hourly.total_cost += usage.cost_usd
        if usage.success:
            hourly.successful_requests += 1
        else:
            hourly.failed_requests += 1
        
        # Update by model
        if usage.model not in hourly.by_model:
            hourly.by_model[usage.model] = {"requests": 0, "tokens": 0, "cost": 0.0}
        hourly.by_model[usage.model]["requests"] += 1
        hourly.by_model[usage.model]["tokens"] += usage.total_tokens
        hourly.by_model[usage.model]["cost"] += usage.cost_usd
        
        # Update by user
        if usage.user_id not in hourly.by_user:
            hourly.by_user[usage.user_id] = {"requests": 0, "tokens": 0, "cost": 0.0}
        hourly.by_user[usage.user_id]["requests"] += 1
        hourly.by_user[usage.user_id]["tokens"] += usage.total_tokens
        hourly.by_user[usage.user_id]["cost"] += usage.cost_usd
        
        # Similar updates for daily metrics
        daily = self.daily_metrics[day_key]
        daily.total_requests += 1
        daily.total_tokens += usage.total_tokens
        daily.total_cost += usage.cost_usd
    
    async def _check_alerts(self, usage: TokenUsage):
        """Check and trigger alerts based on usage"""
        current_hour = datetime.now().strftime('%Y%m%d%H')
        current_day = datetime.now().strftime('%Y%m%d')
        
        # Check hourly system limit
        hourly_alert = self.alerts.get("hourly_limit")
        if hourly_alert and hourly_alert.enabled:
            hourly_cost = await self.get_total_cost("hour")
            if hourly_cost > hourly_alert.threshold_value:
                await self._trigger_alert(
                    hourly_alert,
                    f"Hourly cost limit exceeded: ${hourly_cost:.2f} > ${hourly_alert.threshold_value}"
                )
        
        # Check daily system limit
        daily_alert = self.alerts.get("daily_limit")
        if daily_alert and daily_alert.enabled:
            daily_cost = await self.get_total_cost("day")
            if daily_cost > daily_alert.threshold_value:
                await self._trigger_alert(
                    daily_alert,
                    f"Daily cost limit exceeded: ${daily_cost:.2f} > ${daily_alert.threshold_value}"
                )
        
        # Check user limits
        user_alert = self.alerts.get("user_hourly_limit")
        if user_alert and user_alert.enabled:
            user_cost = await self.get_user_cost(usage.user_id, "hour")
            if user_cost > user_alert.threshold_value:
                await self._trigger_alert(
                    user_alert,
                    f"User {usage.user_id} hourly limit exceeded: ${user_cost:.2f}"
                )
        
        # Spike detection
        spike_alert = self.alerts.get("spike_detection")
        if spike_alert and spike_alert.enabled:
            await self._check_spike(spike_alert)
    
    async def _trigger_alert(self, alert: CostAlert, message: str):
        """Trigger an alert"""
        alert_key = f"{alert.alert_id}:{datetime.now().strftime('%Y%m%d%H')}"
        
        # Avoid duplicate alerts within the same hour
        if alert_key in self.triggered_alerts:
            return
        
        self.triggered_alerts[alert_key] = datetime.now()
        
        # Log alert
        logger.warning(f"Cost Alert [{alert.level.value}] {alert.name}: {message}")
        
        # Send notifications based on channels
        for channel in alert.notification_channels:
            if channel == "log":
                # Already logged above
                pass
            elif channel == "webhook":
                # TODO: Implement webhook notification
                await self._send_webhook_alert(alert, message)
            elif channel == "email":
                # TODO: Implement email notification
                await self._send_email_alert(alert, message)
    
    async def _send_webhook_alert(self, alert: CostAlert, message: str):
        """Send webhook notification"""
        # Implementation would send to configured webhook URL
        logger.info(f"Would send webhook alert: {message}")
    
    async def _send_email_alert(self, alert: CostAlert, message: str):
        """Send email notification"""
        # Implementation would send email
        logger.info(f"Would send email alert: {message}")
    
    async def _check_spike(self, spike_alert: CostAlert):
        """Check for usage spikes"""
        # Compare current hour to average of last 24 hours
        current_hour_cost = await self.get_total_cost("hour")
        
        # Get average hourly cost for last 24 hours
        total_past_cost = 0.0
        hours_checked = 0
        
        for i in range(1, 25):
            past_hour = (datetime.now() - timedelta(hours=i)).strftime('%Y%m%d%H')
            if past_hour in self.hourly_metrics:
                total_past_cost += self.hourly_metrics[past_hour].total_cost
                hours_checked += 1
        
        if hours_checked > 0:
            avg_hourly_cost = total_past_cost / hours_checked
            if avg_hourly_cost > 0 and current_hour_cost > avg_hourly_cost * spike_alert.threshold_value:
                await self._trigger_alert(
                    spike_alert,
                    f"Cost spike detected: ${current_hour_cost:.2f} is {current_hour_cost/avg_hourly_cost:.1f}x normal"
                )
    
    async def get_total_cost(self, period: str = "day") -> float:
        """Get total cost for period (hour/day/month)"""
        if period == "hour":
            key = datetime.now().strftime('%Y%m%d%H')
            if key in self.hourly_metrics:
                return self.hourly_metrics[key].total_cost
        elif period == "day":
            key = datetime.now().strftime('%Y%m%d')
            if key in self.daily_metrics:
                return self.daily_metrics[key].total_cost
        
        # Try Redis
        if self.redis_client:
            try:
                if period == "hour":
                    redis_key = f"metrics:hour:{datetime.now().strftime('%Y%m%d%H')}"
                elif period == "day":
                    redis_key = f"metrics:day:{datetime.now().strftime('%Y%m%d')}"
                else:
                    return 0.0
                
                cost = self.redis_client.hget(redis_key, "total_cost")
                return float(cost) if cost else 0.0
            except Exception as e:
                logger.error(f"Failed to get cost from Redis: {e}")
        
        return 0.0
    
    async def get_user_cost(self, user_id: str, period: str = "day") -> float:
        """Get user's total cost for period"""
        if period == "hour":
            key = datetime.now().strftime('%Y%m%d%H')
            if key in self.hourly_metrics and user_id in self.hourly_metrics[key].by_user:
                return self.hourly_metrics[key].by_user[user_id]["cost"]
        elif period == "day":
            key = datetime.now().strftime('%Y%m%d')
            if key in self.daily_metrics and user_id in self.daily_metrics[key].by_user:
                return self.daily_metrics[key].by_user[user_id]["cost"]
        
        # Try Redis
        if self.redis_client:
            try:
                if period == "hour":
                    redis_key = f"metrics:hour:{datetime.now().strftime('%Y%m%d%H')}"
                elif period == "day":
                    redis_key = f"metrics:day:{datetime.now().strftime('%Y%m%d')}"
                else:
                    return 0.0
                
                cost = self.redis_client.hget(redis_key, f"user:{user_id}:cost")
                return float(cost) if cost else 0.0
            except Exception as e:
                logger.error(f"Failed to get user cost from Redis: {e}")
        
        return 0.0
    
    def get_usage_report(self, period: str = "day") -> Dict[str, Any]:
        """Get usage report for period"""
        if period == "hour":
            key = datetime.now().strftime('%Y%m%d%H')
            metrics = self.hourly_metrics.get(key, UsageMetrics())
        else:
            key = datetime.now().strftime('%Y%m%d')
            metrics = self.daily_metrics.get(key, UsageMetrics())
        
        return {
            "period": period,
            "timestamp": key,
            "total_requests": metrics.total_requests,
            "successful_requests": metrics.successful_requests,
            "failed_requests": metrics.failed_requests,
            "total_tokens": metrics.total_tokens,
            "total_cost_usd": round(metrics.total_cost, 2),
            "by_model": metrics.by_model,
            "by_user": {
                user: {
                    "requests": data["requests"],
                    "tokens": data["tokens"],
                    "cost_usd": round(data["cost"], 2)
                }
                for user, data in list(metrics.by_user.items())[:10]  # Top 10 users
            },
            "by_agent": metrics.by_agent
        }
    
    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status"""
        return {
            "hourly": {
                "spent": asyncio.run(self.get_total_cost("hour")),
                "limit": self.alerts.get("hourly_limit").threshold_value if self.alerts.get("hourly_limit") else None,
                "percentage": None
            },
            "daily": {
                "spent": asyncio.run(self.get_total_cost("day")),
                "limit": self.alerts.get("daily_limit").threshold_value if self.alerts.get("daily_limit") else None,
                "percentage": None
            }
        }
    
    def update_pricing(self, model: str, pricing: ModelPricing):
        """Update pricing for a model"""
        self.pricing[model] = pricing
        logger.info(f"Updated pricing for {model}: ${pricing.input_price_per_1k}/{pricing.output_price_per_1k} per 1k tokens")
    
    def update_alert(self, alert: CostAlert):
        """Update or add an alert configuration"""
        self.alerts[alert.alert_id] = alert
        logger.info(f"Updated alert {alert.alert_id}: {alert.name}")


# Context manager for tracking costs
class CostTracker:
    """Context manager for tracking costs of a specific operation"""
    
    def __init__(
        self,
        cost_monitor: CostMonitor,
        request_id: str,
        user_id: str,
        model: str,
        agent_type: Optional[str] = None,
        request_type: Optional[str] = None
    ):
        self.cost_monitor = cost_monitor
        self.request_id = request_id
        self.user_id = user_id
        self.model = model
        self.agent_type = agent_type
        self.request_type = request_type
        self.input_tokens = 0
        self.output_tokens = 0
        self.success = True
        self.error_message = None
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.success = False
            self.error_message = str(exc_val)
        
        # Track the usage
        await self.cost_monitor.track_usage(
            request_id=self.request_id,
            user_id=self.user_id,
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            agent_type=self.agent_type,
            request_type=self.request_type,
            success=self.success,
            error_message=self.error_message
        )
    
    def set_tokens(self, input_tokens: int, output_tokens: int):
        """Set token counts"""
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens