"""检查手写源文件是否包含中文模块说明。

该脚本只执行低成本自动门禁；复杂代码是否逐行解释仍需按阶段 README 中的
评审清单人工确认，避免用机械字符统计代替真正的代码质量评审。
"""

import re
import sys
from hashlib import sha256
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
SOURCE_SUFFIXES = {".py", ".go", ".ts", ".tsx", ".css", ".proto", ".sql"}
# Protobuf 的 Go/Python 生成目录不属于手写代码，不执行中文和 300 行门禁。
IGNORED_PARTS = {"node_modules", ".venv", "dist", "__pycache__", "generated", "gen"}


def hand_written_sources() -> list[Path]:
    """返回需要执行中文说明检查的手写源文件。"""

    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if any(part in IGNORED_PARTS for part in path.parts):
            continue
        files.append(path)
    return files


def main() -> int:
    """检查源码和阶段 README，失败时输出精确相对路径。"""

    missing_chinese: list[Path] = []
    oversized_sources: list[Path] = []
    for path in hand_written_sources():
        # 读取前 40 行即可覆盖模块注释，避免扫描大文件增加 CI 时间。
        prefix = "\n".join(path.read_text(encoding="utf-8").splitlines()[:40])
        if not CHINESE_PATTERN.search(prefix):
            missing_chinese.append(path.relative_to(PROJECT_ROOT))
        if len(path.read_text(encoding="utf-8").splitlines()) > 300:
            oversized_sources.append(path.relative_to(PROJECT_ROOT))

    stage_readmes = [
        PROJECT_ROOT / "docs" / "stages" / "01-mvp" / "README.md",
        PROJECT_ROOT / "docs" / "stages" / "02-ai-core" / "README.md",
        PROJECT_ROOT / "docs" / "stages" / "03-sre-kubernetes" / "README.md",
        PROJECT_ROOT / "docs" / "stages" / "04-public-demo" / "README.md",
        PROJECT_ROOT / "docs" / "stages" / "05-private-console" / "README.md",
        PROJECT_ROOT / "docs" / "stages" / "06-real-monitoring" / "README.md",
    ]
    for stage_readme in stage_readmes:
        if not stage_readme.is_file():
            print(f"缺少阶段 README: {stage_readme.relative_to(PROJECT_ROOT)}")
            return 1
    if missing_chinese:
        print("以下手写源文件缺少中文模块说明：")
        for path in missing_chinese:
            print(f"- {path}")
        return 1
    if oversized_sources:
        print("以下手写源文件超过 300 行，请检查是否应按职责拆分：")
        for path in oversized_sources:
            print(f"- {path}")
        return 1

    # 示例插件入口哈希必须与清单一致，防止源码变更后留下不可安装的演示。
    for plugin_id in ("http-nginx", "kubernetes", "webhook-notifier"):
        manifest_path = PROJECT_ROOT / "plugins" / plugin_id / "plugin.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        entrypoint = manifest_path.parent / manifest["entrypoint"]
        actual_checksum = f"sha256:{sha256(entrypoint.read_bytes()).hexdigest()}"
        if manifest["checksum"] != actual_checksum:
            print(f"插件 {plugin_id} 清单哈希已过期，请重新计算 checksum。")
            return 1
    print(f"中文说明检查通过，共检查 {len(hand_written_sources())} 个手写源文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
