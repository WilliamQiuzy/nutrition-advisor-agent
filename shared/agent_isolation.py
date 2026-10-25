"""
Agent Isolation Layer for Enhanced Security
Provides sandboxed execution environments for AI agents with controlled permissions
"""

import asyncio
import json
import logging
import os
import tempfile
import time
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import resource
import signal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Permission(Enum):
    """Agent permissions"""
    READ_PATIENT_DATA = "read_patient_data"
    WRITE_PATIENT_DATA = "write_patient_data"
    CALL_EXTERNAL_API = "call_external_api"
    ACCESS_KNOWLEDGE_BASE = "access_knowledge_base"
    EXECUTE_FUNCTIONS = "execute_functions"
    ACCESS_SENSITIVE_DATA = "access_sensitive_data"
    MODIFY_SYSTEM_CONFIG = "modify_system_config"


class IsolationLevel(Enum):
    """Levels of isolation for agents"""
    NONE = 0  # No isolation (development only)
    BASIC = 1  # Basic permission checks
    STANDARD = 2  # Permission checks + resource limits
    STRICT = 3  # Full sandboxing with process isolation
    MAXIMUM = 4  # Separate container/VM (future)


@dataclass
class AgentPermissions:
    """Permission configuration for an agent"""
    agent_type: str
    allowed_permissions: Set[Permission] = field(default_factory=set)
    denied_permissions: Set[Permission] = field(default_factory=set)
    max_execution_time: int = 30  # seconds
    max_memory_mb: int = 512
    max_api_calls: int = 10
    allowed_functions: Set[str] = field(default_factory=set)
    allowed_data_access: Set[str] = field(default_factory=set)


@dataclass
class ExecutionContext:
    """Execution context for isolated agent"""
    agent_id: str
    agent_type: str
    user_id: str
    request_id: str
    permissions: AgentPermissions
    start_time: datetime = field(default_factory=datetime.now)
    api_calls_made: int = 0
    functions_called: List[str] = field(default_factory=list)
    data_accessed: List[str] = field(default_factory=list)
    violations: List[Dict[str, Any]] = field(default_factory=list)


class SecureAgentExecutor:
    """
    Secure executor for AI agents with isolation and permission control
    """
    
    # Default permissions for different agent types
    DEFAULT_PERMISSIONS = {
        "NutritionConsultant": AgentPermissions(
            agent_type="NutritionConsultant",
            allowed_permissions={
                Permission.READ_PATIENT_DATA,
                Permission.ACCESS_KNOWLEDGE_BASE,
                Permission.EXECUTE_FUNCTIONS
            },
            denied_permissions={
                Permission.WRITE_PATIENT_DATA,
                Permission.MODIFY_SYSTEM_CONFIG
            },
            allowed_functions={
                "get_client_profile",
                "get_nutritional_assessment",
                "calculate_nutritional_scores",
                "generate_supplement_plan"
            },
            allowed_data_access={"patient_profile", "nutrition_data", "supplement_db"}
        ),
        "SupplementSpecialist": AgentPermissions(
            agent_type="SupplementSpecialist",
            allowed_permissions={
                Permission.READ_PATIENT_DATA,
                Permission.ACCESS_KNOWLEDGE_BASE,
                Permission.EXECUTE_FUNCTIONS
            },
            allowed_functions={
                "get_supplement_research",
                "analyze_product_quality",
                "check_supplement_interactions"
            },
            allowed_data_access={"supplement_db", "research_db", "interaction_db"}
        ),
        "SafetyAssessor": AgentPermissions(
            agent_type="SafetyAssessor",
            allowed_permissions={
                Permission.READ_PATIENT_DATA,
                Permission.ACCESS_KNOWLEDGE_BASE,
                Permission.EXECUTE_FUNCTIONS,
                Permission.CALL_EXTERNAL_API
            },
            allowed_functions={
                "check_supplement_drug_interactions",
                "analyze_safety_profile",
                "get_contraindications"
            },
            allowed_data_access={"patient_medications", "drug_interaction_db", "safety_db"}
        ),
        "FormulationExpert": AgentPermissions(
            agent_type="FormulationExpert",
            allowed_permissions={
                Permission.ACCESS_KNOWLEDGE_BASE,
                Permission.EXECUTE_FUNCTIONS
            },
            allowed_functions={
                "analyze_supplement_interactions",
                "optimize_supplement_timing",
                "calculate_dosages"
            },
            allowed_data_access={"formulation_db", "dosage_guidelines"}
        ),
        "HealthCoach": AgentPermissions(
            agent_type="HealthCoach",
            allowed_permissions={
                Permission.READ_PATIENT_DATA,
                Permission.ACCESS_KNOWLEDGE_BASE
            },
            denied_permissions={
                Permission.WRITE_PATIENT_DATA,
                Permission.CALL_EXTERNAL_API
            },
            allowed_functions={
                "generate_lifestyle_recommendations",
                "create_wellness_plan"
            },
            allowed_data_access={"patient_goals", "wellness_resources"}
        )
    }
    
    def __init__(
        self,
        isolation_level: IsolationLevel = IsolationLevel.STANDARD,
        custom_permissions: Optional[Dict[str, AgentPermissions]] = None,
        enable_monitoring: bool = True
    ):
        self.isolation_level = isolation_level
        self.permissions = self.DEFAULT_PERMISSIONS.copy()
        if custom_permissions:
            self.permissions.update(custom_permissions)
        self.enable_monitoring = enable_monitoring
        
        # Execution tracking
        self.active_contexts: Dict[str, ExecutionContext] = {}
        self.execution_history: List[ExecutionContext] = []
        
        # Process pool for strict isolation
        self.process_pool = None
        if isolation_level >= IsolationLevel.STRICT:
            self.process_pool = ProcessPoolExecutor(max_workers=4)
    
    async def execute_agent(
        self,
        agent_type: str,
        agent_function: Callable,
        args: tuple = (),
        kwargs: dict = None,
        user_id: str = "unknown",
        request_id: str = None
    ) -> Tuple[bool, Any, ExecutionContext]:
        """
        Execute an agent function with appropriate isolation
        
        Returns:
            Tuple of (success, result, execution_context)
        """
        kwargs = kwargs or {}
        request_id = request_id or str(time.time())
        
        # Get permissions for agent type
        permissions = self.permissions.get(agent_type, AgentPermissions(agent_type=agent_type))
        
        # Create execution context
        context = ExecutionContext(
            agent_id=f"{agent_type}_{request_id}",
            agent_type=agent_type,
            user_id=user_id,
            request_id=request_id,
            permissions=permissions
        )
        
        self.active_contexts[context.agent_id] = context
        
        try:
            # Apply appropriate isolation
            if self.isolation_level == IsolationLevel.NONE:
                result = await self._execute_no_isolation(agent_function, args, kwargs, context)
            elif self.isolation_level == IsolationLevel.BASIC:
                result = await self._execute_basic_isolation(agent_function, args, kwargs, context)
            elif self.isolation_level == IsolationLevel.STANDARD:
                result = await self._execute_standard_isolation(agent_function, args, kwargs, context)
            else:  # STRICT or MAXIMUM
                result = await self._execute_strict_isolation(agent_function, args, kwargs, context)
            
            return True, result, context
            
        except PermissionDenied as e:
            context.violations.append({
                "type": "permission_denied",
                "details": str(e),
                "timestamp": datetime.now().isoformat()
            })
            logger.warning(f"Permission denied for {agent_type}: {e}")
            return False, None, context
            
        except Exception as e:
            context.violations.append({
                "type": "execution_error",
                "details": str(e),
                "timestamp": datetime.now().isoformat()
            })
            logger.error(f"Agent execution error for {agent_type}: {e}")
            return False, None, context
            
        finally:
            # Cleanup
            self.active_contexts.pop(context.agent_id, None)
            self.execution_history.append(context)
            if len(self.execution_history) > 1000:
                self.execution_history = self.execution_history[-500:]
    
    async def _execute_no_isolation(
        self,
        agent_function: Callable,
        args: tuple,
        kwargs: dict,
        context: ExecutionContext
    ) -> Any:
        """Execute with no isolation (development only)"""
        # Direct execution with monitoring
        wrapped_function = self._wrap_with_monitoring(agent_function, context)
        return await wrapped_function(*args, **kwargs)
    
    async def _execute_basic_isolation(
        self,
        agent_function: Callable,
        args: tuple,
        kwargs: dict,
        context: ExecutionContext
    ) -> Any:
        """Execute with basic permission checks"""
        # Wrap function with permission checks
        wrapped_function = self._wrap_with_permissions(agent_function, context)
        wrapped_function = self._wrap_with_monitoring(wrapped_function, context)
        
        return await wrapped_function(*args, **kwargs)
    
    async def _execute_standard_isolation(
        self,
        agent_function: Callable,
        args: tuple,
        kwargs: dict,
        context: ExecutionContext
    ) -> Any:
        """Execute with permission checks and resource limits"""
        # Apply resource limits
        if hasattr(resource, 'setrlimit'):
            # Set memory limit (Unix-like systems)
            soft, hard = resource.getrlimit(resource.RLIMIT_AS)
            resource.setrlimit(
                resource.RLIMIT_AS,
                (context.permissions.max_memory_mb * 1024 * 1024, hard)
            )
        
        # Wrap with all protections
        wrapped_function = self._wrap_with_permissions(agent_function, context)
        wrapped_function = self._wrap_with_monitoring(wrapped_function, context)
        wrapped_function = self._wrap_with_timeout(wrapped_function, context)
        
        return await wrapped_function(*args, **kwargs)
    
    async def _execute_strict_isolation(
        self,
        agent_function: Callable,
        args: tuple,
        kwargs: dict,
        context: ExecutionContext
    ) -> Any:
        """Execute in separate process with full isolation"""
        if not self.process_pool:
            # Fallback to standard isolation
            return await self._execute_standard_isolation(
                agent_function, args, kwargs, context
            )
        
        # Create isolated execution wrapper
        def isolated_execution():
            # In the child process, apply strict limits
            if hasattr(os, 'setpgrp'):
                os.setpgrp()  # Create new process group
            
            # Set resource limits
            if hasattr(resource, 'setrlimit'):
                # Memory limit
                resource.setrlimit(
                    resource.RLIMIT_AS,
                    (context.permissions.max_memory_mb * 1024 * 1024,
                     context.permissions.max_memory_mb * 1024 * 1024)
                )
                # CPU time limit
                resource.setrlimit(
                    resource.RLIMIT_CPU,
                    (context.permissions.max_execution_time,
                     context.permissions.max_execution_time + 5)
                )
            
            # Execute function with monitoring
            try:
                # Create new event loop for the process
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                wrapped = self._wrap_with_permissions(agent_function, context)
                wrapped = self._wrap_with_monitoring(wrapped, context)
                
                result = loop.run_until_complete(wrapped(*args, **kwargs))
                return {"success": True, "result": result, "context": context}
            except Exception as e:
                return {"success": False, "error": str(e), "context": context}
            finally:
                loop.close()
        
        # Execute in process pool
        future = self.process_pool.submit(isolated_execution)
        
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, future.result),
                timeout=context.permissions.max_execution_time
            )
            
            if result["success"]:
                return result["result"]
            else:
                raise Exception(result["error"])
                
        except asyncio.TimeoutError:
            # Kill the process if it times out
            future.cancel()
            raise TimeoutError(f"Agent execution exceeded time limit of {context.permissions.max_execution_time}s")
    
    def _wrap_with_permissions(self, func: Callable, context: ExecutionContext) -> Callable:
        """Wrap function with permission checks"""
        async def wrapped(*args, **kwargs):
            # Create permission-aware proxy objects
            kwargs = self._create_permission_proxies(kwargs, context)
            
            # Execute with permission context
            return await func(*args, **kwargs)
        
        return wrapped
    
    def _wrap_with_monitoring(self, func: Callable, context: ExecutionContext) -> Callable:
        """Wrap function with monitoring"""
        async def wrapped(*args, **kwargs):
            # Monitor function calls
            if hasattr(func, '__name__'):
                context.functions_called.append(func.__name__)
            
            # Execute
            return await func(*args, **kwargs)
        
        return wrapped
    
    def _wrap_with_timeout(self, func: Callable, context: ExecutionContext) -> Callable:
        """Wrap function with timeout"""
        async def wrapped(*args, **kwargs):
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=context.permissions.max_execution_time
            )
        
        return wrapped
    
    def _create_permission_proxies(self, kwargs: dict, context: ExecutionContext) -> dict:
        """Create permission-aware proxy objects for function arguments"""
        proxied_kwargs = {}
        
        for key, value in kwargs.items():
            if key == "fhir_client":
                # Wrap FHIR client with permission checks
                proxied_kwargs[key] = PermissionProxy(
                    value, context, 
                    required_permission=Permission.READ_PATIENT_DATA
                )
            elif key == "knowledge_base":
                proxied_kwargs[key] = PermissionProxy(
                    value, context,
                    required_permission=Permission.ACCESS_KNOWLEDGE_BASE
                )
            else:
                proxied_kwargs[key] = value
        
        return proxied_kwargs
    
    def check_permission(self, context: ExecutionContext, permission: Permission) -> bool:
        """Check if agent has specific permission"""
        if permission in context.permissions.denied_permissions:
            return False
        if permission in context.permissions.allowed_permissions:
            return True
        # Default deny for unlisted permissions
        return False
    
    def check_function_allowed(self, context: ExecutionContext, function_name: str) -> bool:
        """Check if agent can call specific function"""
        if not context.permissions.allowed_functions:
            # If no specific functions listed, check general permission
            return self.check_permission(context, Permission.EXECUTE_FUNCTIONS)
        return function_name in context.permissions.allowed_functions
    
    def check_data_access(self, context: ExecutionContext, data_type: str) -> bool:
        """Check if agent can access specific data type"""
        if not context.permissions.allowed_data_access:
            # If no specific data types listed, check general permission
            return self.check_permission(context, Permission.READ_PATIENT_DATA)
        return data_type in context.permissions.allowed_data_access
    
    @asynccontextmanager
    async def isolated_context(self, agent_type: str, user_id: str):
        """Context manager for isolated agent execution"""
        context = ExecutionContext(
            agent_id=f"{agent_type}_{time.time()}",
            agent_type=agent_type,
            user_id=user_id,
            request_id=str(time.time()),
            permissions=self.permissions.get(agent_type, AgentPermissions(agent_type=agent_type))
        )
        
        self.active_contexts[context.agent_id] = context
        
        try:
            yield context
        finally:
            self.active_contexts.pop(context.agent_id, None)
            self.execution_history.append(context)
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        stats = {
            "active_agents": len(self.active_contexts),
            "total_executions": len(self.execution_history),
            "violations_by_type": {},
            "executions_by_agent": {}
        }
        
        for context in self.execution_history:
            # Count by agent type
            agent_type = context.agent_type
            if agent_type not in stats["executions_by_agent"]:
                stats["executions_by_agent"][agent_type] = 0
            stats["executions_by_agent"][agent_type] += 1
            
            # Count violations
            for violation in context.violations:
                vtype = violation.get("type", "unknown")
                if vtype not in stats["violations_by_type"]:
                    stats["violations_by_type"][vtype] = 0
                stats["violations_by_type"][vtype] += 1
        
        return stats


class PermissionProxy:
    """Proxy object that enforces permissions on method calls"""
    
    def __init__(self, target: Any, context: ExecutionContext, required_permission: Permission):
        self._target = target
        self._context = context
        self._required_permission = required_permission
        self._executor = SecureAgentExecutor()
    
    def __getattr__(self, name):
        # Check permission before allowing access
        if not self._executor.check_permission(self._context, self._required_permission):
            raise PermissionDenied(
                f"Agent {self._context.agent_type} lacks permission {self._required_permission.value}"
            )
        
        # Log access
        self._context.data_accessed.append(f"{self._target.__class__.__name__}.{name}")
        
        # Return original attribute
        attr = getattr(self._target, name)
        
        # If it's a method, wrap it to track calls
        if callable(attr):
            def wrapped(*args, **kwargs):
                # Check API call limit
                if self._required_permission == Permission.CALL_EXTERNAL_API:
                    self._context.api_calls_made += 1
                    if self._context.api_calls_made > self._context.permissions.max_api_calls:
                        raise PermissionDenied(
                            f"Agent exceeded API call limit ({self._context.permissions.max_api_calls})"
                        )
                
                return attr(*args, **kwargs)
            
            return wrapped
        
        return attr


class PermissionDenied(Exception):
    """Exception raised when agent lacks required permission"""
    pass


class TimeoutError(Exception):
    """Exception raised when agent execution times out"""
    pass


# Decorator for easy agent isolation
def isolated_agent(
    agent_type: str,
    isolation_level: IsolationLevel = IsolationLevel.STANDARD
):
    """Decorator to automatically apply isolation to agent functions"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            executor = SecureAgentExecutor(isolation_level=isolation_level)
            
            # Extract user_id and request_id from kwargs if available
            user_id = kwargs.pop("user_id", "unknown")
            request_id = kwargs.pop("request_id", None)
            
            success, result, context = await executor.execute_agent(
                agent_type=agent_type,
                agent_function=func,
                args=args,
                kwargs=kwargs,
                user_id=user_id,
                request_id=request_id
            )
            
            if not success:
                raise Exception(f"Agent execution failed: {context.violations}")
            
            return result
        
        return wrapper
    return decorator