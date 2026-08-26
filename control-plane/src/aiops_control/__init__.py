"""AIOps 控制面顶层包。

包内遵循 domain -> application -> ports <- adapters/api 的依赖方向，
业务规则不会依赖 FastAPI、数据库驱动或具体大模型客户端。
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
