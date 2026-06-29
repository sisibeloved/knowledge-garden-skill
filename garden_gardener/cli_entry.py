from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .config import load_config
from .vault import Vault
from .notion import NotionClient
from .gitutil import Git
from .audit import audit
from .proposal import emit_proposals
from .apply import apply_approved


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="garden")
    p.add_argument("--config", default="_Config/gardener.config.yaml")
    p.add_argument("--vault", default=".")
    p.add_argument("--actor", default="manual_session",
                   choices=["manual_session", "scheduled_run"])
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("weekly-audit")
    sub.add_parser("apply-approved")
    sub.add_parser("triage-inbox")

    args = p.parse_args(argv)
    cfg = load_config(Path(args.config))
    vault = Vault(Path(args.vault))
    git = Git(Path(args.vault))
    client = NotionClient(
        cfg.notion["mcp_endpoint"],
        cfg.notion["proposal_database_id"],
        cfg.notion["projects_database_id"],
    )

    if args.cmd == "weekly-audit":
        if not git.pull():
            print("ABORT: git pull failed; 不基于脏数据跑", file=sys.stderr)
            return 2
        rep = audit(
            vault,
            orphan_age_days=cfg.thresholds["orphan_age_days"],
            stale_days=cfg.thresholds.get("stale_review_days", 90),
        )
        emit_proposals(vault, client, rep, actor=args.actor)
        print(f"audit done: {len(rep.orphans)} orphans, {len(rep.stale)} stale, "
              f"{len(rep.inbox_pending)} inbox")
        return 0

    if args.cmd == "apply-approved":
        if not git.pull():
            print("ABORT: git pull failed", file=sys.stderr)
            return 2
        res = apply_approved(cfg, vault, client, git, actor=args.actor)
        print(f"applied {len(res.applied)}, blocked {len(res.blocked)}")
        return 0

    if args.cmd == "triage-inbox":
        rep = audit(vault)
        print(f"{len(rep.inbox_pending)} inbox items pending triage")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
