#!/usr/bin/env python3
"""AlphaXiv Skill.

Search and retrieve research papers from AlphaXiv API.
"""

import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import urllib.error

BASE_URL = "https://api.alphaxiv.org"
PUBLIC_BASE_URL = "https://alphaxiv.org"
DEFAULT_RETRIES = 2


def _headers(extra: dict = None) -> dict:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    if extra:
        h.update(extra)
    return h


def _api_url(path: str, params: dict = None) -> str:
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return url


def _read_response_bytes(resp, url: str) -> tuple[bytes, bool]:
    try:
        return resp.read(), False
    except http.client.IncompleteRead as e:
        partial = e.partial or b""
        print(f"Warning: incomplete response from {url}; using {len(partial)} partial bytes", file=sys.stderr)
        return partial, True


def _get(path: str, params: dict = None, retries: int = DEFAULT_RETRIES) -> dict | list | None:
    url = _api_url(path, params)
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=_headers())
            with urllib.request.urlopen(req, timeout=30) as resp:
                body, incomplete = _read_response_bytes(resp, url)
            if incomplete and attempt < retries:
                print(f"Warning: retrying incomplete response from {url}", file=sys.stderr)
                time.sleep(0.5)
                continue
            if not body:
                return None
            try:
                return json.loads(body.decode())
            except json.JSONDecodeError as e:
                if incomplete:
                    print(f"Error: incomplete JSON from {url}: {e}", file=sys.stderr)
                    return None
                raise
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"HTTP {e.code}: {body}", file=sys.stderr)
            return None
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                print(f"Warning: request failed for {url}: {e}; retrying", file=sys.stderr)
                time.sleep(0.5)
                continue
            print(f"Error: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return None


def _get_with_curl(path: str, params: dict = None, retries: int = DEFAULT_RETRIES) -> dict | list | None:
    url = _api_url(path, params)
    cmd = ["curl", "-L", "--retry", str(retries), "--retry-delay", "1", "-sS", url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Error: curl fallback failed for {url}: {e}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(f"Error: curl fallback failed for {url}: {proc.stderr.strip()}", file=sys.stderr)
        return None
    if not proc.stdout:
        print(f"Error: curl fallback returned an empty response for {url}", file=sys.stderr)
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"Error: curl fallback returned invalid JSON for {url}: {e}", file=sys.stderr)
        return None


def _get_text(url: str, retries: int = DEFAULT_RETRIES) -> str | None:
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/markdown,text/plain,*/*"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                body, incomplete = _read_response_bytes(resp, url)
            if incomplete and attempt < retries:
                print(f"Warning: retrying incomplete response from {url}", file=sys.stderr)
                time.sleep(0.5)
                continue
            if not body and attempt < retries:
                print(f"Warning: empty response from {url}; retrying", file=sys.stderr)
                time.sleep(0.5)
                continue
            text = body.decode()
            if incomplete:
                print(f"Warning: returning partial markdown from {url}", file=sys.stderr)
            return text or None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"HTTP 404: Markdown report not found for {url}", file=sys.stderr)
            else:
                body = e.read().decode()
                print(f"HTTP {e.code}: {body}", file=sys.stderr)
            return None
        except (http.client.IncompleteRead, http.client.RemoteDisconnected, urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                print(f"Warning: request failed for {url}: {e}; retrying", file=sys.stderr)
                time.sleep(0.5)
                continue
            print(f"Error: {e}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return None


def _extract_paper_id(value: str) -> str | None:
    text = urllib.parse.unquote(value.strip())
    match = re.search(r"\d{4}\.\d{4,5}(?:v\d+)?", text)
    if match:
        return match.group(0)
    return None


def _normalize_paper_id(value: str) -> str | None:
    text = urllib.parse.unquote(value.strip())
    if not text:
        return None

    arxiv_id = _extract_paper_id(text)
    if arxiv_id:
        return arxiv_id

    parsed = urllib.parse.urlparse(text)
    if parsed.scheme or parsed.netloc:
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            candidate = parts[-1]
            if candidate.endswith(".md"):
                candidate = candidate[:-3]
            if candidate.endswith(".pdf"):
                candidate = candidate[:-4]
            return candidate or None
        return None

    if re.fullmatch(r"[A-Za-z0-9_.-]+", text):
        return text
    return None


def _require_paper_id(value: str) -> str | None:
    paper_id = _normalize_paper_id(value)
    if not paper_id:
        print(f"Error: could not extract a paper ID from {value!r}", file=sys.stderr)
        return None
    return paper_id


def _safe_cache_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "paper"


def _cache_path(kind: str, paper_id: str, extension: str) -> str:
    filename = f"{kind}.{extension}"
    return os.path.abspath(os.path.join(_safe_cache_id(paper_id), filename))


def _print_cache_hit(path: str) -> bool:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"Using cached file: {path}")
        return True
    return False


def _save_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        if text and not text.endswith("\n"):
            f.write("\n")
    print(f"Saved file: {path}")


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
        if text and not text.endswith("\n"):
            f.write("\n")


def _write_text_if_missing(path: str, text: str) -> None:
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return
    _write_text(path, text)


def _load_json(path: str) -> dict | list | None:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Warning: could not read cached JSON {path}: {e}", file=sys.stderr)
        return None


def _overview_payload(data):
    if isinstance(data, dict):
        return data.get("data", data)
    return data


def _overview_section_value(data, section: str):
    payload = _overview_payload(data)
    fields = {
        "abstract": "abstract",
        "summary": "summary",
        "overview": "overview",
        "report": "intermediateReport",
        "citations": "citations",
    }
    return payload.get(fields[section]) if isinstance(payload, dict) else None


def _print_overview_section(data, section: str) -> None:
    value = _overview_section_value(data, section)
    if value is None:
        print(f"No {section} found.")
    elif isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print(value)


def _format_overview_section(data, section: str) -> str:
    value = _overview_section_value(data, section)
    if value is None:
        return f"No {section} found."
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, ensure_ascii=False)
    return str(value)


def _format_overview_summary(data) -> str:
    summary = _overview_section_value(data, "summary")
    if not summary:
        return "No summary found."
    if not isinstance(summary, dict):
        return str(summary)

    lines = ["# Summary", ""]
    if summary.get("summary"):
        lines.extend([summary["summary"], ""])
    sections = [
        ("Problem", summary.get("originalProblem")),
        ("Method", summary.get("solution")),
        ("Key Insights", summary.get("keyInsights")),
        ("Results", summary.get("results")),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.extend([f"## {title}", ""])
        for item in items:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _format_overview_citations(data) -> str:
    citations = _overview_section_value(data, "citations")
    if not citations:
        return "No citations found."
    if not isinstance(citations, list):
        return str(citations)

    lines = ["# Citations", ""]
    for citation in citations:
        if not isinstance(citation, dict):
            lines.extend([f"- {citation}", ""])
            continue
        title = citation.get("title") or "Untitled"
        lines.append(f"## {title}")
        if citation.get("fullCitation"):
            lines.extend(["", citation["fullCitation"]])
        if citation.get("justification"):
            lines.extend(["", f"**Relevance:** {citation['justification']}"])
        if citation.get("alphaxivLink"):
            lines.extend(["", f"**AlphaXiv:** {citation['alphaxivLink']}"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _get_overview_data(paper_id: str):
    cache_path = _cache_path("overview", paper_id, "json")
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        print(f"Using cached file: {cache_path}", file=sys.stderr)
        data = _load_json(cache_path)
        if data is not None:
            return data
    version_id, _ = _resolve_uuids(paper_id)
    data = _get(f"/papers/v3/{version_id}/overview/en")
    if not data:
        data = _get_with_curl(f"/papers/v3/{version_id}/overview/en")
    if data:
        _save_text(cache_path, json.dumps(data, indent=2, ensure_ascii=False))
    return data


def _fmt_paper(p: dict) -> str:
    lines = []
    title = p.get("title") or p.get("name", "")
    if title:
        lines.append(f"Title: {title}")
    arxiv_id = p.get("arxivId") or p.get("upid") or p.get("id", "")
    if arxiv_id:
        lines.append(f"arXiv ID: {arxiv_id}")
        lines.append(f"URL: https://alphaxiv.org/abs/{arxiv_id}")
    authors = p.get("authors") or p.get("authorNames") or []
    if isinstance(authors, list) and authors:
        if isinstance(authors[0], dict):
            names = [a.get("name", "") for a in authors]
        else:
            names = authors
        lines.append(f"Authors: {', '.join(names[:5])}" + (" et al." if len(names) > 5 else ""))
    date = p.get("submittedDate") or p.get("firstPublicationDate") or p.get("publishedDate", "")
    if date:
        lines.append(f"Date: {date}")
    abstract = p.get("abstract", "")
    if abstract:
        lines.append(f"Abstract: {abstract[:400]}{'...' if len(abstract) > 400 else ''}")
    return "\n".join(lines)


def _json_block(value) -> list[str]:
    return ["```json", json.dumps(value, indent=2, ensure_ascii=False), "```"]


def _append_metric_lines(lines: list[str], label: str, value) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_label = f"{label} {key.replace('_', ' ')}".strip()
            _append_metric_lines(lines, nested_label, nested)
    elif value not in (None, "", []):
        lines.append(f"- **{label}:** {value}")


def _similar_paper_id(p: dict) -> str:
    return p.get("universal_paper_id") or p.get("canonical_id") or p.get("id") or "paper"


def _organization_names(p: dict) -> list[str]:
    names = []
    for org in p.get("organization_info") or []:
        if isinstance(org, dict) and org.get("name"):
            names.append(org["name"])
        elif isinstance(org, str):
            names.append(org)
    return names


def _format_paper_summary(summary) -> str:
    if not summary:
        return "No summary found.\n"
    if not isinstance(summary, dict):
        return str(summary).strip() + "\n"

    lines = ["# Summary", ""]
    if summary.get("summary"):
        lines.extend([summary["summary"], ""])

    sections = [
        ("Problem", summary.get("originalProblem")),
        ("Method", summary.get("solution")),
        ("Key Insights", summary.get("keyInsights")),
        ("Results", summary.get("results")),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.extend([f"## {title}", ""])
        if isinstance(items, list):
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append(str(items))
        lines.append("")

    extra = {
        key: value
        for key, value in summary.items()
        if key not in {"summary", "originalProblem", "solution", "keyInsights", "results"}
    }
    if extra:
        lines.extend(["## Additional Summary Fields", ""])
        lines.extend(_json_block(extra))

    return "\n".join(lines).strip() + "\n"


def _format_similar_metadata(p: dict, include_title: bool = True) -> str:
    title = p.get("title") or p.get("name") or p.get("id") or "Untitled"
    lines = [f"# {title}", ""] if include_title else []

    lines.extend(["## Metadata", ""])
    if title:
        lines.append(f"- **Title:** {title}")
    if p.get("universal_paper_id"):
        lines.append(f"- **Universal paper ID:** {p['universal_paper_id']}")

    url_id = _similar_paper_id(p)
    if url_id:
        lines.append(f"- **AlphaXiv URL:** https://alphaxiv.org/abs/{url_id}")
    if p.get("github_url"):
        stars = p.get("github_stars")
        suffix = f" ({stars} stars)" if stars is not None else ""
        lines.append(f"- **GitHub:** {p['github_url']}{suffix}")
    if p.get("first_publication_date"):
        lines.append(f"- **First publication date:** {p['first_publication_date']}")
    if p.get("publication_date"):
        lines.append(f"- **Publication date:** {p['publication_date']}")
    if p.get("updated_at"):
        lines.append(f"- **Updated at:** {p['updated_at']}")

    authors = p.get("authors") or []
    if authors:
        lines.append(f"- **Authors:** {', '.join(str(author) for author in authors)}")
    topics = p.get("topics") or []
    if topics:
        lines.append(f"- **Topics:** {', '.join(str(topic) for topic in topics)}")
    organization_names = _organization_names(p)
    if organization_names:
        lines.append(f"- **Organizations:** {', '.join(organization_names)}")

    metrics = p.get("metrics")
    if metrics:
        lines.extend(["", "## Metrics", ""])
        for key, value in metrics.items():
            _append_metric_lines(lines, key.replace("_", " "), value)

    if p.get("abstract"):
        lines.extend(["", "## Abstract", "", p["abstract"]])

    return "\n".join(lines).strip()


def _format_similar_paper_result(p: dict, index: int) -> str:
    title = p.get("title") or p.get("name") or p.get("id") or "Untitled"
    lines = [f"## [{index}] {title}", ""]
    body = _format_similar_metadata(p, include_title=False)
    body = body.replace("## Metadata", "### Metadata")
    body = body.replace("## Metrics", "### Metrics")
    body = body.replace("## Abstract", "### Abstract")
    lines.append(body)
    return "\n".join(lines).strip()


def cmd_search(args):
    data = _get("/search/v2/paper/fast", {"q": args.query, "includePrivate": "false"})
    if not data:
        print("No results found.")
        return
    results = data if isinstance(data, list) else data.get("papers", [])
    results = results[: args.limit]
    if not results:
        print("No results found.")
        return
    for i, item in enumerate(results, 1):
        paper_id = item.get("paperId") or item.get("link", "")
        print(f"\n[{i}] {item.get('title', paper_id)}")
        if paper_id:
            print(f"    arXiv ID: {paper_id}")
            print(f"    URL: https://alphaxiv.org/abs/{paper_id}")


def cmd_paper(args):
    data = _get(f"/papers/v3/{args.id}")
    if not data:
        return
    paper = data.get("data", data) if isinstance(data, dict) else data
    lines = []

    def format_timestamp(value) -> str:
        if value in (None, ""):
            return ""
        try:
            ts = float(value)
        except (TypeError, ValueError):
            return str(value)
        if ts > 10_000_000_000:
            ts /= 1000
        return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()

    title = paper.get("title") or paper.get("name", "")
    if title:
        lines.append(f"Title: {title}")
    arxiv_id = paper.get("arxivId") or paper.get("upid") or paper.get("universalId") or paper.get("id", "")
    if arxiv_id:
        lines.append(f"arXiv ID: {arxiv_id}")
        lines.append(f"URL: https://alphaxiv.org/abs/{arxiv_id}")
    if paper.get("sourceUrl"):
        lines.append(f"Source URL: {paper.get('sourceUrl')}")
    if paper.get("versionLabel"):
        lines.append(f"Version: {paper.get('versionLabel')}")
    first_date = format_timestamp(paper.get("firstPublicationDate") or paper.get("submittedDate"))
    if first_date:
        lines.append(f"First Published: {first_date}")
    pub_date = format_timestamp(paper.get("publicationDate") or paper.get("publishedDate"))
    if pub_date:
        lines.append(f"Published: {pub_date}")
    if paper.get("citationsCount") is not None:
        lines.append(f"Citations: {paper.get('citationsCount')}")

    abstract = paper.get("abstract", "")
    if abstract:
        lines.append(f"Abstract: {abstract}")

    print("\n".join(lines))


def cmd_metadata(args):
    paper_id = _require_paper_id(args.id)
    if not paper_id:
        return
    cache_path = _cache_path("metadata", paper_id, "md")
    if _print_cache_hit(cache_path):
        return
    paper_data = _get(f"/papers/v3/{paper_id}")
    metrics_data = _get(f"/papers/v3/{paper_id}/metrics")
    metadata_data = _get(f"/v2/papers/{paper_id}/metadata")

    paper = paper_data.get("data", paper_data) if isinstance(paper_data, dict) else {}
    metrics = metrics_data.get("data", metrics_data) if isinstance(metrics_data, dict) else {}
    metadata = metadata_data.get("data", metadata_data) if isinstance(metadata_data, dict) else {}
    paper_version = metadata.get("paper_version", {}) if isinstance(metadata, dict) else {}
    paper_group = metadata.get("paper_group", {}) if isinstance(metadata, dict) else {}

    def format_timestamp(value) -> str:
        if value in (None, ""):
            return ""
        try:
            ts = float(value)
        except (TypeError, ValueError):
            return str(value)
        if ts > 10_000_000_000:
            ts /= 1000
        return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()

    def append_field(lines: list[str], label: str, value) -> None:
        if value not in (None, "", []):
            lines.append(f"- **{label}:** {value}")

    arxiv_id = (
        paper.get("arxivId")
        or paper.get("upid")
        or paper.get("universalId")
        or paper_version.get("universal_paper_id")
        or paper_id
    )
    title = paper.get("title") or paper.get("name") or paper_version.get("title") or arxiv_id

    lines = [f"# {title}", ""]

    lines.extend(["## Paper", ""])
    append_field(lines, "arXiv ID", arxiv_id)
    append_field(lines, "AlphaXiv URL", f"https://alphaxiv.org/abs/{arxiv_id}" if arxiv_id else "")
    append_field(lines, "Source URL", paper.get("sourceUrl"))
    append_field(lines, "Version", paper.get("versionLabel") or paper_version.get("version_label"))
    append_field(lines, "First Published", format_timestamp(paper.get("firstPublicationDate") or paper.get("submittedDate")))
    append_field(lines, "Published", format_timestamp(paper.get("publicationDate") or paper.get("publishedDate") or paper_version.get("publication_date")))
    append_field(lines, "Citations", paper.get("citationsCount"))

    abstract = paper.get("abstract") or paper_version.get("abstract")
    if abstract:
        lines.extend(["", "### Abstract", "", abstract])

    lines.extend(["", "## Metrics", ""])
    append_field(lines, "Views", metrics.get("visitsAll", "N/A") if metrics else "N/A")
    append_field(lines, "Votes", metrics.get("publicTotalVotes", "N/A") if metrics else "N/A")
    append_field(lines, "Comments", metrics.get("commentsCount", "N/A") if metrics else "N/A")

    lines.extend(["", "## Metadata", ""])
    topics = paper_group.get("topics", []) if isinstance(paper_group, dict) else []
    if topics:
        append_field(lines, "Topics", ", ".join(topics))
    authors = metadata.get("authors", []) if isinstance(metadata, dict) else []
    if authors:
        names = [author.get("full_name", "") for author in authors if isinstance(author, dict)]
        append_field(lines, "Authors", ", ".join(name for name in names if name))
    orgs = metadata.get("organization_info", []) if isinstance(metadata, dict) else []
    if orgs:
        names = [org.get("name", "") for org in orgs if isinstance(org, dict)]
        append_field(lines, "Institutions", ", ".join(name for name in names if name))
    implementation = metadata.get("implementation", {}) if isinstance(metadata, dict) else {}
    if implementation and implementation.get("url"):
        stars = implementation.get("stars", 0)
        append_field(lines, "GitHub", f"{implementation.get('url')} ({stars} stars)")

    citation = paper_version.get("citation", {}) if isinstance(paper_version, dict) else {}
    bibtex = citation.get("bibtex") or paper.get("citationBibtex")
    if bibtex:
        lines.extend(["", "### BibTeX", "", "```bibtex", bibtex, "```"])

    _save_text(cache_path, "\n".join(lines))


def cmd_metrics(args):
    data = _get(f"/papers/v3/{args.id}/metrics")
    if not data:
        return
    d = data.get("data", data) if isinstance(data, dict) else data
    print(f"arXiv ID: {args.id}")
    print(f"Views:    {d.get('visitsAll', 'N/A')}")
    print(f"Votes:    {d.get('publicTotalVotes', 'N/A')}")
    print(f"Comments: {d.get('commentsCount', 'N/A')}")


def _resolve_uuids(id_or_arxiv: str) -> tuple[str, str]:
    """Return (versionId, groupId) for a given arXiv ID or UUID.
    If already a UUID, fetch paper to get both. If arXiv ID, fetch paper."""
    data = _get(f"/papers/v3/{id_or_arxiv}")
    if not data:
        return id_or_arxiv, id_or_arxiv
    p = data.get("data", data) if isinstance(data, dict) else data
    return p.get("versionId", id_or_arxiv), p.get("groupId", id_or_arxiv)


def _get_required_overview_data(paper_id: str):
    data = _get_overview_data(paper_id)
    if not data:
        version_id, _ = _resolve_uuids(paper_id)
        status = _get(f"/papers/v3/{version_id}/overview/status")
        if status:
            print(f"Overview status: {json.dumps(status, indent=2)}")
    return data


def cmd_overview_summary(args):
    paper_id = _require_paper_id(args.id)
    if not paper_id:
        return
    cache_path = _cache_path("overview_summary", paper_id, "md")
    if _print_cache_hit(cache_path):
        return
    data = _get_required_overview_data(paper_id)
    if data:
        _save_text(cache_path, _format_overview_summary(data))


def cmd_overview_walkthrough(args):
    paper_id = _require_paper_id(args.id)
    if not paper_id:
        return
    cache_path = _cache_path("overview_walkthrough", paper_id, "md")
    if _print_cache_hit(cache_path):
        return
    data = _get_required_overview_data(paper_id)
    if data:
        _save_text(cache_path, _format_overview_section(data, "overview"))


def cmd_overview_citations(args):
    paper_id = _require_paper_id(args.id)
    if not paper_id:
        return
    cache_path = _cache_path("overview_citations", paper_id, "md")
    if _print_cache_hit(cache_path):
        return
    data = _get_required_overview_data(paper_id)
    if data:
        _save_text(cache_path, _format_overview_citations(data))


def cmd_overview_report(args):
    paper_id = _require_paper_id(args.input)
    if not paper_id:
        return
    cache_path = _cache_path("report", paper_id, "md")
    if _print_cache_hit(cache_path):
        return
    data = _get_overview_data(paper_id)
    report = _overview_section_value(data, "report") if data else None
    if report:
        _save_text(cache_path, report if isinstance(report, str) else json.dumps(report, indent=2, ensure_ascii=False))
        return
    print("Warning: could not get report from overview; falling back to public markdown endpoint", file=sys.stderr)
    url = f"{PUBLIC_BASE_URL}/overview/{urllib.parse.quote(paper_id)}.md"
    text = _get_text(url)
    if text:
        _save_text(cache_path, text)


def cmd_fulltext(args):
    paper_id = _require_paper_id(args.input)
    if not paper_id:
        return
    cache_path = _cache_path("fulltext", paper_id, "md")
    if _print_cache_hit(cache_path):
        return
    url = f"{PUBLIC_BASE_URL}/abs/{urllib.parse.quote(paper_id)}.md"
    text = _get_text(url)
    if text:
        _save_text(cache_path, text)


def cmd_similar(args):
    paper_id = _require_paper_id(args.id)
    if not paper_id:
        return
    data = _get(f"/papers/v3/{paper_id}/similar-papers", {"limit": str(args.limit)})
    if not data:
        data = _get_with_curl(f"/papers/v3/{paper_id}/similar-papers", {"limit": str(args.limit)})
    if not data:
        return
    papers = data if isinstance(data, list) else data.get("data", [])
    if not papers:
        print("No similar papers found.")
        return
    lines = [f"# Similar Papers for {paper_id}", ""]
    for i, p in enumerate(papers, 1):
        related_id = _similar_paper_id(p)
        _write_text_if_missing(_cache_path("metadata", related_id, "md"), _format_similar_metadata(p))
        _write_text_if_missing(_cache_path("overview_summary", related_id, "md"), _format_paper_summary(p.get("paper_summary")))
        lines.extend([_format_similar_paper_result(p, i), ""])
    print("\n".join(lines).strip())


def cmd_feed(args):
    params = {
        "pageNum": "1",
        "pageSize": str(args.limit),
        "sort": args.sort,
        "interval": args.interval,
    }
    data = _get("/papers/v3/feed", params)
    if not data:
        return
    papers = data.get("papers", data) if isinstance(data, dict) else data
    if not papers:
        print("No papers found.")
        return
    for i, p in enumerate(papers, 1):
        print(f"\n[{i}]")
        print(_fmt_paper(p))


def cmd_implementations(args):
    _, group_id = _resolve_uuids(args.id)
    data = _get(f"/papers/v3/{group_id}/implementations")
    if not data:
        return
    d = data.get("data", data) if isinstance(data, dict) else data
    ax = d.get("alphaXivImplementations", [])
    resources = d.get("paperResources", [])
    if not ax and not resources:
        print("No implementations found.")
        return
    if ax:
        print("AlphaXiv Implementations:")
        for item in ax:
            print(f"  [{item.get('type','')}] {item.get('url','')}")
    if resources:
        print("Paper Resources:")
        for item in resources:
            print(f"  [{item.get('type','')}] {item.get('url','')} - {item.get('description','')}")


def cmd_metadata_legacy(args):
    data = _get(f"/v2/papers/{args.id}/metadata")
    if not data:
        return
    d = data.get("data", data) if isinstance(data, dict) else data
    pv = d.get("paper_version", {})
    pg = d.get("paper_group", {})
    print(f"Title: {pv.get('title', '')}")
    print(f"arXiv ID: {pv.get('universal_paper_id', '')}")
    print(f"Version: {pv.get('version_label', '')}")
    print(f"Published: {pv.get('publication_date', '')}")
    topics = pg.get("topics", [])
    if topics:
        print(f"Topics: {', '.join(topics)}")
    authors = d.get("authors", [])
    if authors:
        names = [a.get("full_name", "") for a in authors]
        print(f"Authors: {', '.join(names)}")
    orgs = d.get("organization_info", [])
    if orgs:
        org_names = [o.get("name", "") for o in orgs]
        print(f"Institutions: {', '.join(org_names)}")
    impl = d.get("implementation", {})
    if impl and impl.get("url"):
        print(f"GitHub: {impl.get('url', '')} ({impl.get('stars', 0)} stars)")
    citation = pv.get("citation", {})
    if citation and citation.get("bibtex"):
        print(f"\nBibTeX:\n{citation.get('bibtex', '')}")


def main():
    parser = argparse.ArgumentParser(description="AlphaXiv API skill")
    sub = parser.add_subparsers(dest="command", required=True)

    # Output: ranked search results with title, arXiv ID, and AlphaXiv URL.
    # Search is intentionally not cached because it is query-oriented and can
    # change frequently.
    p_search = sub.add_parser("search", help="Search papers")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)

    # Output cache: ./<paper_id>/metadata.md with Paper, Metrics, and
    # Metadata sections. It combines the old paper, metrics, and metadata
    # commands into one structured record.
    p_meta = sub.add_parser("metadata", help="Get structured paper metadata")
    p_meta.add_argument("id", help="arXiv ID, UUID, arXiv URL, or AlphaXiv URL")

    # Output cache: ./<paper_id>/overview.json plus
    # ./<paper_id>/overview_summary.md. Formats the API summary JSON as
    # Markdown instead of exposing the raw JSON.
    p_summary = sub.add_parser("summary", help="Get AI overview summary")
    p_summary.add_argument("id", help="arXiv ID, UUID, arXiv URL, or AlphaXiv URL")

    # Output cache: ./<paper_id>/overview_walkthrough.md with the API overview
    # section. This is the shorter narrative walkthrough, not the full report.
    p_walkthrough = sub.add_parser("walkthrough", help="Get AI overview walkthrough")
    p_walkthrough.add_argument("id", help="arXiv ID, UUID, arXiv URL, or AlphaXiv URL")

    # Output cache: ./<paper_id>/overview_citations.md with relevant citations
    # from the overview API.
    p_citations = sub.add_parser("citations", help="Get overview citations")
    p_citations.add_argument("id", help="arXiv ID, UUID, arXiv URL, or AlphaXiv URL")

    # Output cache: ./<paper_id>/report.md from the overview JSON report.
    # If that report is unavailable, falls back to the public markdown endpoint.
    # Use report when the desired output is the fuller research-analysis report,
    # not the shorter walkthrough output.
    p_report = sub.add_parser("report", help="Get markdown report for a paper")
    p_report.add_argument("input", help="arXiv ID, arXiv URL, or AlphaXiv URL")

    # Output cache: ./<paper_id>/fulltext.md with extracted public paper text.
    p_fulltext = sub.add_parser("fulltext", help="Get public markdown full text of a paper")
    p_fulltext.add_argument("input", help="arXiv ID, arXiv URL, or AlphaXiv URL")

    # Output: fresh similar-paper search results. The search response itself is
    # not cached; each returned paper's metadata.md and overview_summary.md are
    # stored under that paper's own ./<paper_id>/ folder for reuse.
    p_similar = sub.add_parser("similar", help="Get similar papers")
    p_similar.add_argument("id", help="arXiv ID, UUID, arXiv URL, or AlphaXiv URL")
    p_similar.add_argument("--limit", type=int, default=10)

    if False:
        # Hidden commands. Keep the parser wiring here so these commands can be
        # restored without touching their command handlers, but do not expose
        # them in argparse.
        p_paper = sub.add_parser("paper", help="Get paper details")
        p_paper.add_argument("id", help="arXiv ID or UUID")

        p_metrics = sub.add_parser("metrics", help="Get paper metrics")
        p_metrics.add_argument("id", help="arXiv ID or UUID")

        p_feed = sub.add_parser("feed", help="Get feed papers")
        p_feed.add_argument("--sort", default="Hot",
            choices=["Hot", "Comments", "Views", "Likes", "GitHub", "Twitter (X)"])
        p_feed.add_argument("--interval", default="7 Days",
            choices=["3 Days", "7 Days", "30 Days"])
        p_feed.add_argument("--limit", type=int, default=10)

        p_impl = sub.add_parser("implementations", help="Get paper implementations")
        p_impl.add_argument("id", help="arXiv ID or UUID")

        p_legacy_meta = sub.add_parser("legacy_metadata", help="Get paper authors, institutions, topics, GitHub")
        p_legacy_meta.add_argument("id", help="arXiv ID")

    args = parser.parse_args()

    {
        "search": cmd_search,  # no need cache
        "metadata": cmd_metadata,
        "summary": cmd_overview_summary,
        "walkthrough": cmd_overview_walkthrough,
        "citations": cmd_overview_citations,
        "report": cmd_overview_report,
        "fulltext": cmd_fulltext,
        "similar": cmd_similar,  # no need cache
        # "paper": cmd_paper,
        # "metrics": cmd_metrics,
        # "feed": cmd_feed,
        # "implementations": cmd_implementations,
        # "legacy_metadata": cmd_metadata_legacy,
    }[args.command](args)


if __name__ == "__main__":
    main()
