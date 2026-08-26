"""实验 API 的依赖健康超时测试。"""

import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parents[1] / "app"))

import main


def test_healthz_converts_slow_dependency_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    """Redis 或 Docker DNS 卡住时，API 仍应在上游探针超时前返回 503。"""

    monkeypatch.setattr(main.redis_client, "ping", lambda: time.sleep(1.5))
    started = time.monotonic()
    with pytest.raises(HTTPException) as captured:
        main.healthz()
    assert captured.value.status_code == 503
    assert time.monotonic() - started < 1.25
