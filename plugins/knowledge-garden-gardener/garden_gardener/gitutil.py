from __future__ import annotations
import subprocess
from pathlib import Path


class Git:
    """git 操作封装:pull(基于最新)、commit(带 gardener 前缀+notion-id)、revert。"""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                              text=True, check=check)

    def pull(self) -> bool:
        """拉取最新(rebase)。返回是否成功;失败由调用方决定中止。"""
        r = self._run("pull", "--rebase", check=False)
        return r.returncode == 0

    def commit_all(self, risk: str, summary: str, *, notion_id: str | None = None) -> str:
        """暂存全部并提交,返回 commit sha。message 形如:
        gardener(L2): create Concepts/X (approved 2026-06-28-001)
        """
        msg = f"gardener({risk}): {summary}"
        if notion_id:
            msg += f" (approved {notion_id})"
        self._run("add", "-A")
        self._run("commit", "-m", msg)
        return self._run("rev-parse", "HEAD").stdout.strip()

    def revert(self, sha: str) -> None:
        """生成一个反向 commit 撤销指定 commit。"""
        self._run("revert", "--no-edit", sha)
