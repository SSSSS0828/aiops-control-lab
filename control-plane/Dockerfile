# 控制面使用多阶段无缓存安装，保持镜像可复现且体积可控。
FROM python:3.12-slim AS runtime

# 默认仍使用官方 PyPI；网络受限环境可以通过 Compose build args 选择可信镜像源。
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL}

WORKDIR /app
COPY control-plane/pyproject.toml ./
COPY control-plane/src ./src
COPY sdk/python /sdk
COPY plugins /plugins
RUN pip install /sdk
RUN pip install .

# 非 root 用户只能访问应用目录，不能修改容器系统文件。
RUN useradd --system --uid 10001 aiops && chown -R aiops:aiops /app /plugins
USER aiops
EXPOSE 8000
CMD ["uvicorn", "aiops_control.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
