"""插件清单领域模型。"""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PluginManifest:
    """控制面验证并启动插件所需的最小不可变信息。"""

    plugin_id: str
    name: str
    version: str
    api_version: str
    entrypoint: str
    checksum: str
    capabilities: tuple[str, ...]
    permissions: tuple[str, ...]
    config_schema: dict[str, object] = field(default_factory=dict)
