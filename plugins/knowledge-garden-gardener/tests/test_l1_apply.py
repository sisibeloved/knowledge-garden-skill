"""L1 自动 apply 引擎测试。

fixture: vault(含 §3.1 骨架 + git init) + force_filesystem。
Config 手搓含完整 L1 operations(backfill_frontmatter/add_wikilink/add_tag)。
"""
from datetime import date
from garden_gardener.vault import Vault
from garden_gardener.gitutil import Git
from garden_gardener.config import Config
from garden_gardener.frontmatter import dump, parse
from garden_gardener.l1_apply import apply_l1


def _cfg(operations=None) -> Config:
    """完整 L1 配置。operations 可覆盖以测试"某类被关掉"。"""
    ops = operations or {
        "append_raw": "L0",
        "backfill_frontmatter": "L1",
        "add_wikilink": "L1",
        "add_tag": "L1",
        "create_evergreen": "L2",
    }
    return Config(
        raw={},
        risk_levels={
            "L0": {"auto": True}, "L1": {"auto": True},
            "L2": {"auto": False}, "L3": {"auto": False},
        },
        operations=ops,
        actors={"manual_session": ["L0", "L1", "L2", "L3"],
                "scheduled_run": ["L0", "L1"]},
        hard_disabled=[{"unsanctioned": "create_evergreen"}],
        thresholds={"batch_l1_max": 50}, access={}, notion={},
    )


def _note(vault, rel, fm, body):
    Vault(vault).write(rel, dump(fm, body), risk_level="L2")


# ---------- backfill_frontmatter ----------

def test_backfill_fills_missing_fields(vault, force_filesystem):
    _note(vault, "Concepts/RAG.md",
          {"title": "RAG 检索"},  # 缺 id/created_at/updated_at/status
          "正文")
    v, git = Vault(vault), Git(vault)
    res = apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    assert res.backfilled == 1
    fm, _ = parse(v.read("Concepts/RAG.md"))
    assert fm["id"] == "evergreen-rag-检索"
    assert fm["created_at"] == date.today().isoformat()
    assert fm["updated_at"] == date.today().isoformat()
    assert fm["status"] == "evergreen"
    assert res.commits  # 有 commit


def test_backfill_skips_complete_notes(vault, force_filesystem):
    _note(vault, "Concepts/Full.md",
          {"id": "x", "title": "Full", "created_at": "2026-01-01",
           "updated_at": "2026-01-02", "status": "evergreen"}, "正文")
    v, git = Vault(vault), Git(vault)
    res = apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    assert res.backfilled == 0  # 无需补
    # backfill 无变更 → 不产生 backfill commit(linked/tagged 也 0 → commits 空)
    assert res.commits == []


def test_backfill_slug_falls_back_when_no_title(vault, force_filesystem):
    _note(vault, "Concepts/NoTitle.md", {}, "正文")  # 无 title
    v, git = Vault(vault), Git(vault)
    apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    fm, _ = parse(v.read("Concepts/NoTitle.md"))
    assert fm["id"] == "evergreen-note"  # slugify(空) → "note"


# ---------- add_wikilink ----------

def test_wikilink_added_when_body_mentions_other_title(vault, force_filesystem):
    # A 正文提到 B 的标题 → A 应补 [[B]]
    _note(vault, "Concepts/A.md", {"title": "RAG 检索"}, "参考了 向量数据库 的设计")
    _note(vault, "Concepts/B.md", {"title": "向量数据库"}, "向量数据库是...")
    v, git = Vault(vault), Git(vault)
    res = apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    assert res.linked >= 1
    fm_a, body_a = parse(v.read("Concepts/A.md"))
    assert "[[向量数据库]]" in fm_a["links"]
    assert "[[向量数据库]]" in body_a  # 正文首处替换


def test_wikilink_no_self_reference(vault, force_filesystem):
    # 笔记正文含自己的标题 → 不自引用
    _note(vault, "Concepts/Self.md", {"title": "自指"}, "自指 是一种自指现象")
    v, git = Vault(vault), Git(vault)
    apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    fm, body = parse(v.read("Concepts/Self.md"))
    assert "[[自指]]" not in (fm.get("links") or [])
    assert "[[自指]]" not in body


def test_wikilink_respects_word_boundary(vault, force_filesystem):
    # "检索" 不应误中 "全文检索系统"(中文邻接 → 非边界)
    _note(vault, "Concepts/A.md", {"title": "笔记A"}, "全文检索系统 很有用")
    _note(vault, "Concepts/B.md", {"title": "检索"}, "检索 是...")
    v, git = Vault(vault), Git(vault)
    apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    fm_a, body_a = parse(v.read("Concepts/A.md"))
    # "检索" 被"全文"和"系统"夹着 → 边界不匹配 → 不补链
    assert "[[检索]]" not in body_a
    assert "[[检索]]" not in (fm_a.get("links") or [])


def test_wikilink_no_duplicate(vault, force_filesystem):
    # 已在 links 里的不重复加
    _note(vault, "Concepts/A.md",
          {"title": "A", "links": ["[[向量数据库]]"]},
          "向量数据库 很好")
    _note(vault, "Concepts/B.md", {"title": "向量数据库"}, "x")
    v, git = Vault(vault), Git(vault)
    apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    fm, _ = parse(v.read("Concepts/A.md"))
    assert fm["links"].count("[[向量数据库]]") == 1


# ---------- add_tag ----------

def test_tag_added_when_empty_and_english_frequent(vault, force_filesystem):
    _note(vault, "Concepts/Eng.md", {"title": "T"},
          "Retrieval retrieval generation generation embedding")
    # retrieval×2, generation×2, embedding×1 → tags=[retrieval, generation]
    v, git = Vault(vault), Git(vault)
    res = apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    assert res.tagged == 1
    fm, _ = parse(v.read("Concepts/Eng.md"))
    assert "retrieval" in fm["tags"]
    assert "generation" in fm["tags"]
    assert "embedding" not in fm["tags"]  # 只出现 1 次


def test_tag_not_overwriting_existing(vault, force_filesystem):
    _note(vault, "Concepts/Has.md",
          {"title": "T", "tags": ["手写标签"]},
          "retrieval retrieval generation generation")
    v, git = Vault(vault), Git(vault)
    apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    fm, _ = parse(v.read("Concepts/Has.md"))
    assert fm["tags"] == ["手写标签"]  # 不覆盖


# ---------- batch + actor ----------

def test_batch_max_truncates(vault, force_filesystem):
    # 3 篇都缺 id,但 batch_max=2 → 只补 2 篇
    for i in range(3):
        _note(vault, f"Concepts/N{i}.md", {"title": f"N{i}"}, "x")
    v, git = Vault(vault), Git(vault)
    res = apply_l1(_cfg(), v, git, actor="manual_session", batch_max=2)
    assert res.backfilled == 2


def test_l1_runs_under_scheduled_actor(vault, force_filesystem):
    # scheduled_run 能力上限 [L0,L1],L1 仍 AUTO(L1 不受 actor 能力上限约束)
    _note(vault, "Concepts/S.md", {"title": "S"}, "x")
    v, git = Vault(vault), Git(vault)
    res = apply_l1(_cfg(), v, git, actor="scheduled_run", batch_max=50)
    assert res.backfilled == 1


def test_disabled_l1_op_skipped(vault, force_filesystem):
    # add_tag 映射到 L2(非自动档)→ decide 返回非 AUTO → 跳过加标签
    _note(vault, "Concepts/T.md", {"title": "T"},
          "retrieval retrieval generation generation")
    v, git = Vault(vault), Git(vault)
    cfg = _cfg(operations={
        "backfill_frontmatter": "L1", "add_wikilink": "L1",
        "add_tag": "L2",  # 故意升档
        "append_raw": "L0", "create_evergreen": "L2",
    })
    res = apply_l1(cfg, v, git, actor="manual_session", batch_max=50)
    assert res.tagged == 0
    fm, _ = parse(v.read("Concepts/T.md"))
    assert "tags" not in fm  # 没加


def test_each_op_class_separate_commit(vault, force_filesystem):
    # A 同时触发 backfill + 补链 + 加标签;B 完整(只作补链目标) → 3 个 commit
    _note(vault, "Concepts/A.md", {"title": "A"},
          "向量数据库 向量数据库 retrieval retrieval generation generation")
    _note(vault, "Concepts/B.md",
          {"id": "b", "title": "向量数据库", "created_at": "2026-01-01",
           "updated_at": "2026-01-01", "status": "evergreen", "tags": ["已有"]},
          "x")
    v, git = Vault(vault), Git(vault)
    res = apply_l1(_cfg(), v, git, actor="manual_session", batch_max=50)
    # 只 A 触发三类(B 完整、已有 tags、正文无 A 标题)
    assert res.backfilled == 1 and res.linked == 1 and res.tagged == 1
    assert len(res.commits) == 3
