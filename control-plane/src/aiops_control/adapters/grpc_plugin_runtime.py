"""独立进程 gRPC 插件运行时。

输入：经过目录白名单限制的 plugin.yaml。
数据流：清单校验 -> SHA-256 校验 -> 启动候选进程 -> gRPC 健康检查 -> 原子注册。
输出：当前健康插件快照和通用 RPC 调用结果。
副作用：创建子进程与 Unix Socket；卸载时会终止所管理的子进程。
并发：注册表由锁保护，耗时健康检查不会在锁内执行。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any

import grpc
import yaml
from google.protobuf import struct_pb2

from aiops_control.domain.plugin import PluginManifest

SUPPORTED_API_VERSION = "v1"
ALLOWED_CAPABILITIES = frozenset(
    {
        "DiscoveryProvider",
        "TelemetryProvider",
        "Analyzer",
        "ActionProvider",
        "KnowledgeProvider",
        "Notifier",
    }
)
ALLOWED_PERMISSIONS = frozenset(
    {
        "network.http.outbound",
        "kubernetes.nodes.read",
        "kubernetes.workloads.read",
        "kubernetes.events.read",
        "kubernetes.deployments.patch.allowed_namespaces",
    }
)


@dataclass(slots=True)
class RunningPlugin:
    """控制面持有的插件进程与通信句柄。"""

    manifest: PluginManifest
    process: subprocess.Popen[bytes]
    socket_path: Path
    channel: grpc.Channel


class GrpcPluginRuntime:
    """管理插件安装、原子升级、调用和卸载。"""

    def __init__(self, plugin_root: Path, runtime_root: Path) -> None:
        self._plugin_root = plugin_root.resolve()
        self._runtime_root = runtime_root.resolve()
        self._runtime_root.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, RunningPlugin] = {}
        self._lock = RLock()

    def install(self, manifest_path: Path) -> PluginManifest:
        """验证并启动插件；新版本健康后才替换旧版本。"""

        manifest_file = manifest_path.resolve()
        # 路径必须位于插件根目录内，阻止 API 借清单读取并执行任意文件。
        if not manifest_file.is_relative_to(self._plugin_root):
            raise ValueError("插件清单不在允许目录内")
        manifest = self._load_manifest(manifest_file)
        entrypoint = (manifest_file.parent / manifest.entrypoint).resolve()
        if not entrypoint.is_relative_to(manifest_file.parent.resolve()):
            raise ValueError("插件入口不能逃逸插件目录")
        self._verify_checksum(entrypoint, manifest.checksum)

        # 候选版本使用独立 Socket，健康检查失败不会影响当前已注册版本。
        # Unix Socket 通常限制在约 107 字节；使用身份哈希避免长插件名耗尽路径预算。
        socket_identity = f"{manifest.plugin_id}:{manifest.version}".encode()
        socket_name = f"{sha256(socket_identity).hexdigest()[:16]}.sock"
        socket_path = self._runtime_root / socket_name
        # 在启动子进程前给出可理解错误，避免插件只留下底层 gRPC bind 失败日志。
        if len(str(socket_path).encode("utf-8")) > 100:
            raise ValueError("插件运行目录过长，请配置更短的 AIOPS_PLUGIN_RUNTIME_ROOT")
        socket_path.unlink(missing_ok=True)
        environment = os.environ.copy()
        environment["AIOPS_PLUGIN_SOCKET"] = str(socket_path)
        command = (
            [sys.executable, str(entrypoint)] if entrypoint.suffix == ".py" else [str(entrypoint)]
        )
        process = subprocess.Popen(command, env=environment, cwd=manifest_file.parent)
        channel = grpc.insecure_channel(f"unix:{socket_path}")
        candidate = RunningPlugin(manifest, process, socket_path, channel)
        try:
            self._wait_until_healthy(candidate)
        except Exception:
            self._stop(candidate)
            raise

        # 锁内只交换引用；旧进程在锁外停止，避免阻塞其他读取操作。
        with self._lock:
            previous = self._plugins.get(manifest.plugin_id)
            self._plugins[manifest.plugin_id] = candidate
        if previous is not None:
            self._stop(previous)
        return manifest

    def list_plugins(self) -> list[PluginManifest]:
        """返回当前已注册插件的不可变清单快照。"""

        with self._lock:
            return [item.manifest for item in self._plugins.values()]

    def call(self, plugin_id: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        """调用一个已注册插件的白名单 RPC。"""

        allowed_methods = {
            "Describe",
            "Health",
            "Discover",
            "Analyze",
            "Plan",
            "Execute",
            "Verify",
            "Rollback",
        }
        if method not in allowed_methods:
            raise ValueError(f"插件方法 {method} 不在允许列表内")
        with self._lock:
            plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise KeyError(f"插件 {plugin_id} 未安装")
        return self._invoke(plugin.channel, method, payload)

    def uninstall(self, plugin_id: str) -> None:
        """先从注册表摘除插件，再停止进程并清理 Socket。"""

        with self._lock:
            plugin = self._plugins.pop(plugin_id, None)
        if plugin is not None:
            self._stop(plugin)

    def close(self) -> None:
        """停止所有受管插件，供控制面优雅关闭时调用。"""

        with self._lock:
            plugin_ids = list(self._plugins)
        for plugin_id in plugin_ids:
            self.uninstall(plugin_id)

    def _load_manifest(self, path: Path) -> PluginManifest:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("插件清单根节点必须是映射")
        raw_config_schema = raw.get("config_schema", {})
        if not isinstance(raw_config_schema, dict):
            raise ValueError("插件 config_schema 必须是映射")
        manifest = PluginManifest(
            plugin_id=str(raw["id"]),
            name=str(raw["name"]),
            version=str(raw["version"]),
            api_version=str(raw["api_version"]),
            entrypoint=str(raw["entrypoint"]),
            checksum=str(raw["checksum"]),
            capabilities=tuple(raw.get("capabilities", [])),
            permissions=tuple(raw.get("permissions", [])),
            config_schema={str(key): value for key, value in raw_config_schema.items()},
        )
        if manifest.api_version != SUPPORTED_API_VERSION:
            raise ValueError(f"不支持插件 API {manifest.api_version}")
        if not set(manifest.capabilities).issubset(ALLOWED_CAPABILITIES):
            raise ValueError("插件声明了未知能力")
        if not set(manifest.permissions).issubset(ALLOWED_PERMISSIONS):
            raise ValueError("插件声明了未授权权限")
        if manifest.config_schema and manifest.config_schema.get("type") != "object":
            raise ValueError("插件 config_schema 顶层 type 必须是 object")
        return manifest

    def _verify_checksum(self, entrypoint: Path, expected: str) -> None:
        if not entrypoint.is_file():
            raise ValueError(f"插件入口不存在: {entrypoint}")
        actual = sha256(entrypoint.read_bytes()).hexdigest()
        if expected != f"sha256:{actual}":
            raise ValueError("插件入口 SHA-256 校验失败")

    def _wait_until_healthy(self, plugin: RunningPlugin) -> None:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if plugin.process.poll() is not None:
                raise RuntimeError("插件在健康检查前退出")
            try:
                response = self._invoke(plugin.channel, "Health", {})
                if response.get("status") == "ok":
                    return
            except grpc.RpcError:
                time.sleep(0.2)
        raise TimeoutError("插件健康检查超时")

    def _invoke(
        self,
        channel: grpc.Channel,
        method: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        request = struct_pb2.Struct()
        request.update(payload)
        rpc = channel.unary_unary(
            f"/aiops.plugin.v1.PluginService/{method}",
            request_serializer=struct_pb2.Struct.SerializeToString,
            response_deserializer=struct_pb2.Struct.FromString,
        )
        response = rpc(request, timeout=5)
        return dict(response)

    def _stop(self, plugin: RunningPlugin) -> None:
        plugin.channel.close()
        plugin.process.terminate()
        try:
            plugin.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            plugin.process.kill()
            plugin.process.wait(timeout=3)
        plugin.socket_path.unlink(missing_ok=True)
