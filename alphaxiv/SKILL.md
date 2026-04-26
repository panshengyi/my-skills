---
name: alphaxiv
description: Search and retrieve research papers from AlphaXiv. Use when asked to search papers by title or topic, get paper details/metadata/metrics, retrieve AI overviews, markdown reports, full text, feed papers, similar papers, or implementations.
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

**Get paper details:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py paper 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py paper 1706.03762v1
```

**Get paper metrics (views, votes, comments):**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py metrics 1706.03762
```

**Get AI overview:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py overview 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py overview 1706.03762 --section summary
```
Saves or reuses `./alphaxiv_1706.03762_overview.json` in the current working directory, then prints the requested section.
The `overview` section is a shorter paper walkthrough focused on the core method, experiments, figures, and conclusions. The `report` section is a longer structured research analysis covering authors, institutions, research landscape, motivation, methodology, findings, and impact.

**Get public markdown overview report:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py lookup 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py lookup https://arxiv.org/abs/1706.03762
```
Uses the overview JSON first and saves its `report` section to `./alphaxiv_1706.03762_overview.md`. Falls back to `alphaxiv.org/overview/{PAPER_ID}.md` only when the overview report is unavailable.
Use `lookup` when you want the fuller research-analysis report rather than the shorter `overview --section overview` walkthrough.

**Get public markdown full text:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py fulltext 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py fulltext https://arxiv.org/pdf/1706.03762
```
Saves or reuses `./alphaxiv_1706.03762_fulltext.md` in the current working directory.

**Get similar papers:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py similar 1706.03762 --limit 5
```

**Get feed papers:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py feed --sort Hot --interval "7 Days" --limit 10
```

**Get paper implementations (code repos):**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py implementations 1706.03762
```

**Get paper authors, institutions, topics, GitHub, and BibTeX when available:**
```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py metadata 1706.03762
```

No token is required for the supported commands: `search`, `paper`, `metrics`, `metadata`, `similar`, `feed`, `implementations`, `overview`, `lookup`, `fulltext`.

## Notes

- arXiv IDs like `1706.03762` or `1706.03762v1` are accepted
- `overview`, `lookup`, and `fulltext` write large outputs to the current working directory and reuse existing non-empty cache files before downloading
- `overview --section` options: `abstract`, `summary`, `overview`, `report`, `citations`
- `overview --section overview` is the shorter narrative walkthrough; `overview --section report` is the fuller structured research analysis
- `lookup` also accepts arXiv and AlphaXiv URLs; it prefers the overview JSON `report` section and falls back to the public markdown endpoint
- `fulltext` accepts the same inputs and saves extracted paper text from `alphaxiv.org/abs/{PAPER_ID}.md`
- `overview` returns the English AI overview
- `metadata` prints BibTeX by default when AlphaXiv provides it
- Feed `--sort` options: `Hot`, `Comments`, `Views`, `Likes`, `GitHub`, `Twitter (X)`
- Feed `--interval` options: `3 Days`, `7 Days`, `30 Days`
