from __future__ import annotations
import shutil
import subprocess
from pathlib import Path


class Vault:
    """vault 访问抽象层:对外暴露读写原语,内部探测 CLI 不可用则降级 filesystem。

    风险判定不在此层做(在 apply.py 编排层经 risk.decide 校验);此处 risk_level
    仅用于 run-log 记录。路径安全:禁止写到 vault 根之外。
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.mode = "cli" if _cli_available() else "filesystem"

    def _resolve(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        # 禁止路径逃逸到 vault 外
        try:
            p.relative_to(self.root)
        except ValueError:
            raise ValueError(f"path escapes vault: {rel}")
        return p

    def read(self, rel: str) -> str:
        return self._resolve(rel).read_text(encoding="utf-8")

    def read_glob(self, pattern: str) -> list[Path]:
        return sorted(self.root.glob(pattern))

    def exists(self, rel: str) -> bool:
        return self._resolve(rel).exists()

    def write(self, rel: str, content: str, *, risk_level: str = "L0") -> Path:
        p = self._resolve(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def append(self, rel: str, content: str, *, risk_level: str = "L0") -> Path:
        p = self._resolve(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return p


def _cli_available() -> bool:
    """探测 Obsidian CLI 是否可用。filesystem 测试用 monkeypatch 关掉。"""
    exe = shutil.which("obsidian")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False
