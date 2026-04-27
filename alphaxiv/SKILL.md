---
name: alphaxiv
description: Search and retrieve research papers from AlphaXiv. Use when asked to search papers by title or topic, get structured paper metadata, retrieve AI overviews, markdown reports, full text, or similar papers.
argument-hint: <command> [arxiv-id] [options]
---

# AlphaXiv Skill

AlphaXiv is a platform built on top of arXiv that adds social features, AI-generated overviews, benchmarks, and community engagement to research papers.

## Usage

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py <command> [options]
```

## Commands

**Search papers:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py search "attention is all you need" --limit 5
```

**Get paper metadata:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py metadata 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py metadata 1706.03762v1
```
Prints Markdown with `Paper`, `Metrics`, and `Metadata` sections. This combines the previous paper, metrics, and metadata outputs into one structured result.
Saves or reuses `./1706.03762/metadata.md`.

**Get AI overview summary:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py summary 1706.03762
```
Saves or reuses `./1706.03762/overview.json`, then saves a Markdown summary to `./1706.03762/overview_summary.md`.

**Get AI overview walkthrough:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py walkthrough 1706.03762
```
Saves or reuses `./1706.03762/overview.json`, then saves the shorter narrative walkthrough to `./1706.03762/overview_walkthrough.md`.

**Get overview citations:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py citations 1706.03762
```
Saves or reuses `./1706.03762/overview.json`, then saves relevant citations to `./1706.03762/overview_citations.md`.

**Get public markdown overview report:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py report 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py report https://arxiv.org/abs/1706.03762
```
Uses the overview JSON first and saves its `report` section to `./1706.03762/report.md`. Falls back to `alphaxiv.org/overview/{PAPER_ID}.md` only when the overview report is unavailable.
Use `report` when you want the fuller research-analysis report rather than the shorter `walkthrough` output.

**Get public markdown full text:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py fulltext 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py fulltext https://arxiv.org/pdf/1706.03762
```
Saves or reuses `./1706.03762/fulltext.md`.

**Get similar papers:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py similar 1706.03762 --limit 5
```
Saves or reuses `./1706.03762/similar_limit_5.txt`.

No token is required for the supported commands: `search`, `metadata`, `similar`, `summary`, `walkthrough`, `citations`, `report`, `fulltext`.

## Notes

- arXiv IDs like `1706.03762` or `1706.03762v1` are accepted
- Commands with a paper ID cache outputs under `./{PAPER_ID}/`; `search` is not cached
- `metadata` includes the paper abstract; there is no separate overview abstract command
- `summary` formats the AlphaXiv summary JSON as Markdown
- `walkthrough` is the shorter narrative walkthrough; `report` is the fuller structured research analysis
- `report` also accepts arXiv and AlphaXiv URLs; it prefers the overview JSON `report` section and falls back to the public markdown endpoint
- `fulltext` accepts the same inputs and saves extracted paper text from `alphaxiv.org/abs/{PAPER_ID}.md`
- `metadata` prints BibTeX by default when AlphaXiv provides it
