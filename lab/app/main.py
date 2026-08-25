"""三层故障实验室的 API 服务。

请求经过 Nginx 到达本服务，再访问 Redis 形成可观察依赖链。
服务只写入演示计数器，不处理真实用户数据。
"""

import os
from hmac import compare_digest
from time import sleep

from fastapi import FastAPI, Header, HTTPException
from fault_state import SUPPORTED_APPLICATION_FAULTS, FaultState
from pydantic import BaseModel, Field
from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

app = FastAPI(title="AIOps Fault Lab API")
redis_client = Redis.from_url(
    os.getenv("REDIS_URL", "redis://lab-redis:6379/0"),
    decode_responses=True,
    # 依赖中断必须在健康探针超时前转成明确的 HTTP 503，不能让上游只看到连接超时。
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
    retry=Retry(NoBackoff(), 0),
)
fault_state = FaultState()
lab_control_token = os.getenv("AIOPS_LAB_CONTROL_TOKEN", "")


class FaultActivationRequest(BaseModel):
    """实验故障控制端点接受的有界持续时间。"""

    duration_seconds: int = Field(ge=1, le=120)


def _require_control_token(provided_token: str) -> None:
    """使用常量时间比较验证私网控制令牌，缺少配置时安全关闭。"""

    if not lab_control_token:
        raise HTTPException(status_code=503, detail="实验控制端点未配置")
    if not compare_digest(provided_token, lab_control_token):
        raise HTTPException(status_code=401, detail="实验控制令牌无效")


def _apply_request_faults() -> None:
    """在访问真实依赖前应用延迟和 5xx，形成可观测的网关症状。"""

    if fault_state.active("request_latency"):
        sleep(2.0)
    if fault_state.active("http_5xx"):
        raise HTTPException(status_code=503, detail="已注入 HTTP 5xx 实验故障")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """同时验证 API 进程和 Redis 依赖。"""

    _apply_request_faults()
    try:
        redis_client.ping()
    except RedisError as error:
        raise HTTPException(status_code=503, detail="Redis 依赖不可用") from error
    return {"status": "ok", "service": "lab-api", "dependency": "lab-redis"}


@app.get("/work")
def work() -> dict[str, int]:
    """增加计数器，为指标、日志和依赖故障生成稳定流量。"""

    _apply_request_faults()
    try:
        value = redis_client.incr("lab:requests")
    except RedisError as error:
        raise HTTPException(status_code=503, detail="无法写入 Redis") from error
    return {"request_count": value}


@app.put("/__control/faults/{scenario}", include_in_schema=False)
def activate_fault(
    scenario: str,
    payload: FaultActivationRequest,
    x_lab_control_token: str = Header(default=""),
) -> dict[str, str | int]:
    """在私网中启用一个有硬超时的应用故障。"""

    _require_control_token(x_lab_control_token)
    if scenario not in SUPPORTED_APPLICATION_FAULTS:
        raise HTTPException(status_code=404, detail="应用故障场景未注册")
    fault_state.activate(scenario, payload.duration_seconds)
    return {
        "status": "active",
        "scenario": scenario,
        "duration_seconds": payload.duration_seconds,
    }


@app.delete("/__control/faults/{scenario}", include_in_schema=False)
def clear_fault(
    scenario: str,
    x_lab_control_token: str = Header(default=""),
) -> dict[str, str]:
    """提前清理故障；重复清理保持成功以便后台任务安全重试。"""

    _require_control_token(x_lab_control_token)
    if scenario not in SUPPORTED_APPLICATION_FAULTS:
        raise HTTPException(status_code=404, detail="应用故障场景未注册")
    fault_state.clear(scenario)
    return {"status": "cleared", "scenario": scenario}
