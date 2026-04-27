---
name: alphaxiv
description: Search and retrieve research papers from AlphaXiv. Use when asked to search papers by title, topic, or ID; get structured paper metadata; retrieve AI summaries, reports, walkthroughs, citations, full text, or similar papers.
argument-hint: <command> [paper-id-or-query] [options]
---

# AlphaXiv Skill

AlphaXiv is a platform built on top of arXiv that provides searchable paper metadata, AI-generated overviews, structured reports, citations, related papers, and extracted markdown full text.

Use the explicit interpreter:

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py <command> [options]
```

## When to Use

- The user provides an arXiv ID, arXiv URL, AlphaXiv URL, paper title, or paper topic.
- The user asks for a research paper summary, explanation, analysis, related work, citations, or exact paper details.
- The user needs a paper-specific context source that is faster and easier to inspect than a raw PDF.

## Recommended Workflow

1. If the exact paper is unknown, run `search` with keywords, a title, or an ID-like query.
2. For a known paper, start with `metadata` and `summary` to establish the title, abstract, publication details, metrics, problem, method, key insights, and results.
3. If the user needs deeper understanding, use `report` for the fuller structured research analysis.
4. If the user needs content closer to the paper body, use `walkthrough`.
5. Use `fulltext` only when a very specific detail is needed, such as an equation, table, section wording, appendix detail, or exact experimental setting.
6. Use `citations` to identify key supporting papers cited by the work.
7. Use `similar` to find related work with similar topics or abstracts.

## Commands

### Search for Papers

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py search "attention is all you need" --limit 5
```

`search` returns ranked candidates with titles, arXiv IDs when available, AlphaXiv URLs, authors, and short abstracts. It is a utility command for finding the target paper and is intentionally not cached because search results can change.

### Get Paper Metadata

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py metadata 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py metadata https://arxiv.org/abs/1706.03762
```

`metadata` saves or reuses `./1706.03762/metadata.md`. It prints Markdown with `Paper`, `Metrics`, and `Metadata` sections, including title, arXiv ID, AlphaXiv URL, source URL, version, first published date, latest published date, citation count, abstract, views, votes, comments, topics, authors, institutions, and BibTeX when AlphaXiv provides it.

Use this first when you need the paper identity, abstract, bibliographic details, or basic AlphaXiv metrics.

### Get a Short AI Summary

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py summary 1706.03762
```

`summary` saves or reuses `./1706.03762/overview.json`, then writes `./1706.03762/overview_summary.md`. It formats the AlphaXiv overview summary into Markdown sections such as `Problem`, `Method`, `Key Insights`, and `Results`.

Use this with `metadata` for the fastest useful overview of a paper.

### Get the Structured Report

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py report 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py report https://alphaxiv.org/abs/1706.03762
```

`report` saves or reuses `./1706.03762/report.md`. It prefers the `report` section from the cached overview JSON and falls back to the public markdown endpoint `https://alphaxiv.org/overview/{PAPER_ID}.md` only when needed.

Use this for deeper analysis: broader research context, motivation, methodology, evaluation, results, limitations, and significance. This is usually the best next step after `metadata` and `summary`.

### Get the Paper Walkthrough

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py walkthrough 1706.03762
```

`walkthrough` saves or reuses `./1706.03762/overview.json`, then writes `./1706.03762/overview_walkthrough.md`. It is shorter than `report` and follows the paper content more narratively, often including figures and section-level explanations.

Use this when the user wants to understand how the paper unfolds or asks about the paper's concrete method flow.

### Get Supporting Citations

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py citations 1706.03762
```

`citations` saves or reuses `./1706.03762/overview.json`, then writes `./1706.03762/overview_citations.md`. It lists key related papers cited by or relevant to the target paper, with short relevance explanations and AlphaXiv links when available.

Use this to trace the foundations of a paper or identify important prior work.

### Get Similar Papers

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py similar 1706.03762 --limit 5
```

`similar` saves or reuses `./1706.03762/similar_limit_5.txt`. It returns papers similar to the target paper, including title, AlphaXiv URL, authors, and abstract snippets.

Use this to expand the related-work set beyond the paper's cited foundation.

### Get Extracted Full Text

```bash
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py fulltext 1706.03762
/opt/miniconda3/bin/python3 ${CLAUDE_SKILL_DIR}/scripts/alphaxiv.py fulltext https://arxiv.org/pdf/1706.03762
```

`fulltext` saves or reuses `./1706.03762/fulltext.md` from `https://alphaxiv.org/abs/{PAPER_ID}.md`.

Use this as a fallback for precise details that are not present in `metadata`, `summary`, `report`, or `walkthrough`. It is much larger and less selective than the other outputs.

## Choosing the Right Output

Recent tests with paper `2509.23586` produced these approximate output sizes:

| Command | Cached output | Approx. size | Best use |
| --- | --- | ---: | --- |
| `metadata` | `./2509.23586/metadata.md` | 1.7 KB | Paper identity, abstract, dates, URLs, metrics, authors, topics |
| `summary` | `./2509.23586/overview_summary.md` | 2.7 KB | Fast conceptual overview of problem, method, insights, and results |
| `citations` | `./2509.23586/overview_citations.md` | 2.8 KB | Key supporting papers and why they matter |
| `similar` | `./2509.23586/similar_limit_5.txt` | 3.3 KB | Related work with similar topics or abstracts |
| `walkthrough` | `./2509.23586/overview_walkthrough.md` | 10 KB | Narrative, paper-body-oriented explanation with concrete flow |
| `report` | `./2509.23586/report.md` | 21 KB | Fuller research analysis and structured interpretation |
| `fulltext` | `./2509.23586/fulltext.md` | 82 KB | Exact paper details, original wording, equations, tables, sections |

Prefer smaller, structured outputs first. Do not jump to `fulltext` unless the question requires exact details that the curated outputs do not contain.

## Paper ID Handling

Paper-specific commands accept plain arXiv IDs, versioned arXiv IDs, AlphaXiv UUIDs, and common arXiv or AlphaXiv URLs. Pass the user's input directly to the script; the script extracts the paper ID before requesting data or checking the cache.

| Input | Extracted paper ID |
| --- | --- |
| `1706.03762` | `1706.03762` |
| `1706.03762v1` | `1706.03762v1` |
| `https://arxiv.org/abs/1706.03762` | `1706.03762` |
| `https://arxiv.org/pdf/1706.03762` | `1706.03762` |
| `https://alphaxiv.org/abs/1706.03762` | `1706.03762` |

## Caching

- `search` is not cached.
- Paper-specific commands cache under `./{PAPER_ID}/` in the current working directory.
- `summary`, `walkthrough`, `citations`, and `report` share `./{PAPER_ID}/overview.json`.
- Cache-hit messages such as `Using cached file: .../overview.json` may appear on stderr for commands that reuse the shared overview JSON.
- Cached files are reused before making network requests.

## Error Handling

- No authentication is required for the supported commands.
- If a public markdown endpoint returns 404, AlphaXiv has not generated that report or full text yet.
- Network interruptions can produce retry warnings. The script retries incomplete reads and may fall back to `curl` for overview JSON.
- If a command returns no useful content, try `metadata` to confirm the paper exists, then try the next broader output: `summary`, `report`, `walkthrough`, and finally `fulltext`.

Supported public commands: `search`, `metadata`, `summary`, `walkthrough`, `citations`, `report`, `fulltext`, `similar`.
