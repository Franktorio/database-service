# ~/src/services/system/monitoring.py

import time
from datetime import datetime, timezone
from functools import wraps
from collections import deque
from dataclasses import dataclass
from typing import Literal

from config.settings import MONITORING_SETTINGS

NOT_FOUND = MONITORING_SETTINGS.NOT_FOUND
INVALID_DATA = MONITORING_SETTINGS.INVALID_DATA
TOO_SOON = MONITORING_SETTINGS.TOO_SOON
DENIED = MONITORING_SETTINGS.DENIED
ALLOWED = MONITORING_SETTINGS.ALLOWED


@dataclass(slots=True)
class EndpointMetaData:
    recorded_at: datetime
    func_name: str
    method: str
    was_exception: bool
    response_time: float
    response_status_code: int


@dataclass(slots=True)
class OperationMetaData:
    recorded_at: datetime
    func_name: str
    operation_type: Literal["read", "write"]
    was_exception: bool
    operation_time: float


@dataclass(slots=True)
class RedisOperationMetaData:
    recorded_at: datetime
    func_name: str
    operation_type: Literal["read", "write"]
    cache_miss: bool
    was_exception: bool
    response_status_code: int
    operation_time: float


class MonitoringService:
    def __init__(self) -> None:
        max_samples = MONITORING_SETTINGS.sample_max_amount

        # Recent samples for debugging/inspection
        self.api_data: deque[EndpointMetaData] = deque(maxlen=max_samples)
        self.operation_data: deque[OperationMetaData] = deque(maxlen=max_samples)
        self.redis_operation_data: deque[RedisOperationMetaData] = deque(maxlen=max_samples)

        # Running metrics
        self.metrics: dict[str, int | float] = {
            # API
            "api_total_requests": 0,
            "api_total_exceptions": 0,
            "api_total_response_time": 0.0,
            "api_avg_response_time": 0.0,
            "api_max_response_time": 0.0,

            # Database operations
            "db_total_reads": 0,
            "db_total_writes": 0,
            "db_total_exceptions": 0,
            "db_total_read_time": 0.0,
            "db_total_write_time": 0.0,
            "db_avg_read_time": 0.0,
            "db_avg_write_time": 0.0,
            "db_max_read_time": 0.0,
            "db_max_write_time": 0.0,

            # Redis operations
            "redis_total_reads": 0,
            "redis_total_writes": 0,
            "redis_total_exceptions": 0,
            "redis_total_cache_misses": 0,
            "redis_total_read_time": 0.0,
            "redis_total_write_time": 0.0,
            "redis_avg_read_time": 0.0,
            "redis_avg_write_time": 0.0,
            "redis_max_read_time": 0.0,
            "redis_max_write_time": 0.0,
        }

    def record_endpoint(self, data: EndpointMetaData) -> None:
        self.api_data.append(data)

        self.metrics["api_total_requests"] += 1
        self.metrics["api_total_response_time"] += data.response_time
        self.metrics["api_max_response_time"] = max(
            self.metrics["api_max_response_time"],
            data.response_time,
        )

        if data.was_exception:
            self.metrics["api_total_exceptions"] += 1

        self.metrics["api_avg_response_time"] = (
            self.metrics["api_total_response_time"]
            / self.metrics["api_total_requests"]
        )

    def record_operation(self, data: OperationMetaData) -> None:
        self.operation_data.append(data)

        if data.operation_type == "read":
            self.metrics["db_total_reads"] += 1
            self.metrics["db_total_read_time"] += data.operation_time
            self.metrics["db_max_read_time"] = max(
                self.metrics["db_max_read_time"],
                data.operation_time,
            )

            self.metrics["db_avg_read_time"] = (
                self.metrics["db_total_read_time"]
                / self.metrics["db_total_reads"]
            )

        else:
            self.metrics["db_total_writes"] += 1
            self.metrics["db_total_write_time"] += data.operation_time
            self.metrics["db_max_write_time"] = max(
                self.metrics["db_max_write_time"],
                data.operation_time,
            )

            self.metrics["db_avg_write_time"] = (
                self.metrics["db_total_write_time"]
                / self.metrics["db_total_writes"]
            )

        if data.was_exception:
            self.metrics["db_total_exceptions"] += 1

    def record_redis_operation(self, data: RedisOperationMetaData) -> None:
        self.redis_operation_data.append(data)

        if data.cache_miss:
            self.metrics["redis_total_cache_misses"] += 1

        if data.operation_type == "read":
            self.metrics["redis_total_reads"] += 1
            self.metrics["redis_total_read_time"] += data.operation_time
            self.metrics["redis_max_read_time"] = max(
                self.metrics["redis_max_read_time"],
                data.operation_time,
            )

            self.metrics["redis_avg_read_time"] = (
                self.metrics["redis_total_read_time"]
                / self.metrics["redis_total_reads"]
            )

        else:
            self.metrics["redis_total_writes"] += 1
            self.metrics["redis_total_write_time"] += data.operation_time
            self.metrics["redis_max_write_time"] = max(
                self.metrics["redis_max_write_time"],
                data.operation_time,
            )

            self.metrics["redis_avg_write_time"] = (
                self.metrics["redis_total_write_time"]
                / self.metrics["redis_total_writes"]
            )

        if data.was_exception:
            self.metrics["redis_total_exceptions"] += 1
            
    def get_metrics(self) -> dict[str, int | float]:
        return self.metrics
    
    def get_recent_samples(self) -> dict[str, list[EndpointMetaData | OperationMetaData | RedisOperationMetaData]]:
        return {
            "api_data": list(self.api_data),
            "operation_data": list(self.operation_data),
            "redis_operation_data": list(self.redis_operation_data),
        }

    def get_snapshot(self) -> dict:
        """Return the versioned, JSON-ready monitoring contract used by dashboards."""
        recent = self.get_recent_samples()
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": dict(self.metrics),
            "recent": {
                "api": [
                    {
                        "recorded_at": sample.recorded_at.isoformat(),
                        "func_name": sample.func_name,
                        "method": sample.method,
                        "was_exception": sample.was_exception,
                        "response_time": sample.response_time,
                        "response_status_code": sample.response_status_code,
                    }
                    for sample in recent["api_data"]
                ],
                "database": [
                    {
                        "recorded_at": sample.recorded_at.isoformat(),
                        "func_name": sample.func_name,
                        "operation_type": sample.operation_type,
                        "was_exception": sample.was_exception,
                        "operation_time": sample.operation_time,
                    }
                    for sample in recent["operation_data"]
                ],
                "redis": [
                    {
                        "recorded_at": sample.recorded_at.isoformat(),
                        "func_name": sample.func_name,
                        "operation_type": sample.operation_type,
                        "cache_miss": sample.cache_miss,
                        "was_exception": sample.was_exception,
                        "response_status_code": sample.response_status_code,
                        "operation_time": sample.operation_time,
                    }
                    for sample in recent["redis_operation_data"]
                ],
            },
        }

_monitoring_service = MonitoringService()


def monitored(measuring: Literal["api", "db", "redis"], operation_type: Literal["read", "write"] | None = None):
    """
    Decorator to monitor API endpoints, database operations, and Redis operations.
    """
    
    if measuring != "api" and operation_type is None:
        raise ValueError("operation_type must be specified for db and redis monitoring")
    
    def decorator(func):

        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            was_exception = False
            response_status_code = 200  # Default to 200, can be overridden
            request = next(
                (value for value in (*args, *kwargs.values()) if hasattr(value, "method")),
                None,
            )
            request_method = getattr(request, "method", "GET")
            
            result = None  # Initialize result to None in case of exceptions before assignment
            
            try:
                result = await func(*args, **kwargs)
                if measuring == "api":
                    response_status_code = getattr(result, "status_code", 200)
                return result
            except Exception as e:
                print(f"Exception in monitored function '{func.__name__}': {e}")
                if measuring == "api":
                    response_status_code = getattr(e, "status_code", 500)
                    if response_status_code >= 500: # Count server errors as exceptions
                        was_exception = True 
                else:
                    was_exception = True
                raise # Re-raise the exception after recording the metrics
            finally:
                end_time = time.perf_counter()
                elapsed_time = end_time - start_time

                if measuring == "api":
                    metadata = EndpointMetaData(
                        recorded_at=datetime.now(timezone.utc),
                        func_name=func.__name__,
                        method=request_method,
                        was_exception=was_exception,
                        response_time=elapsed_time,
                        response_status_code=response_status_code,
                    )
                    _monitoring_service.record_endpoint(metadata)
                elif measuring == "db":
                    metadata = OperationMetaData(
                        recorded_at=datetime.now(timezone.utc),
                        func_name=func.__name__,
                        operation_type=operation_type,
                        was_exception=was_exception,
                        operation_time=elapsed_time,
                    )
                    _monitoring_service.record_operation(metadata)
                elif measuring == "redis":
                    cache_miss = result is None or result == NOT_FOUND  # Assuming a cache miss if the result is None or NOT_FOUND
                    metadata = RedisOperationMetaData(
                        recorded_at=datetime.now(timezone.utc),
                        func_name=func.__name__,
                        operation_type=operation_type,
                        cache_miss=cache_miss,
                        was_exception=was_exception,
                        response_status_code=response_status_code,
                        operation_time=elapsed_time,
                    )
                    _monitoring_service.record_redis_operation(metadata)
        return wrapper
    return decorator

def get_monitoring_service() -> MonitoringService:
    """Get the singleton instance of the MonitoringService."""
    return _monitoring_service