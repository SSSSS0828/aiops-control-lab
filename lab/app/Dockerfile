# 实验 API 是隔离业务目标，不与 AIOps 控制面共享依赖。
FROM python:3.12-alpine

# 默认使用官方 PyPI，国内云服务器可通过构建参数选择可信镜像源。
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# 业务入口与故障状态机分离，便于单独测试超时和并发边界。
COPY main.py fault_state.py ./
RUN adduser -D -u 10002 lab && chown -R lab:lab /app
USER lab
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
