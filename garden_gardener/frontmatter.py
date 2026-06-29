from __future__ import annotations
import yaml

DELIM = "---"


def parse(text: str) -> tuple[dict, str]:
    """把 markdown 文本拆成 (frontmatter dict, body)。无 frontmatter 则返回 ({}, text)。"""
    if not text.startswith(DELIM):
        return {}, text
    # 跳过开头的 --- 及其后的换行
    rest = text[len(DELIM):]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    # 找闭合的 ---
    end = rest.find(f"\n{DELIM}")
    if end == -1:
        return {}, text
    yaml_block = rest[:end]
    body = rest[end + len(DELIM) + 1:].lstrip("\r\n")
    return yaml.safe_load(yaml_block) or {}, body


def dump(fm: dict, body: str) -> str:
    """把 frontmatter dict + body 组装成带 YAML frontmatter 的 markdown 文本。"""
    yaml_block = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"{DELIM}\n{yaml_block}\n{DELIM}\n{body}"
