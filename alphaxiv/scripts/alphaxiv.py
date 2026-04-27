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


def cmd_paper_metadata(args):
    cache_path = _cache_path("paper_metadata", args.id, "md")
    if _print_cache_hit(cache_path):
        return
    paper_data = _get(f"/papers/v3/{args.id}")
    metrics_data = _get(f"/papers/v3/{args.id}/metrics")
    metadata_data = _get(f"/v2/papers/{args.id}/metadata")

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
        or args.id
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


def cmd_overview(args):
    section_ext = "md" if args.section in ("overview", "report") else "json" if args.section in ("summary", "citations") else "txt"
    section_cache_path = _cache_path(f"overview_{args.section}", args.id, section_ext)
    if _print_cache_hit(section_cache_path):
        return
    data = _get_overview_data(args.id)
    if not data:
        version_id, _ = _resolve_uuids(args.id)
        status = _get(f"/papers/v3/{version_id}/overview/status")
        if status:
            print(f"Overview status: {json.dumps(status, indent=2)}")
        return
    _save_text(section_cache_path, _format_overview_section(data, args.section))


def cmd_lookup(args):
    paper_id = _extract_paper_id(args.input)
    if not paper_id:
        print(f"Error: could not extract an arXiv paper ID from {args.input!r}", file=sys.stderr)
        return
    cache_path = _cache_path("overview", paper_id, "md")
    if _print_cache_hit(cache_path):
        return
    data = _get_overview_data(paper_id)
    report = _overview_section_value(data, "report") if data else None
    if report:
        _save_text(cache_path, report if isinstance(report, str) else json.dumps(report, indent=2, ensure_ascii=False))
        return
    print("Warning: could not get report from overview; falling back to public markdown lookup", file=sys.stderr)
    url = f"{PUBLIC_BASE_URL}/overview/{urllib.parse.quote(paper_id)}.md"
    text = _get_text(url)
    if text:
        _save_text(cache_path, text)


def cmd_fulltext(args):
    paper_id = _extract_paper_id(args.input)
    if not paper_id:
        print(f"Error: could not extract an arXiv paper ID from {args.input!r}", file=sys.stderr)
        return
    cache_path = _cache_path("fulltext", paper_id, "md")
    if _print_cache_hit(cache_path):
        return
    url = f"{PUBLIC_BASE_URL}/abs/{urllib.parse.quote(paper_id)}.md"
    text = _get_text(url)
    if text:
        _save_text(cache_path, text)


def cmd_similar(args):
    cache_path = _cache_path(f"similar_limit_{args.limit}", args.id, "txt")
    if _print_cache_hit(cache_path):
        return
    data = _get(f"/papers/v3/{args.id}/similar-papers", {"limit": str(args.limit)})
    if not data:
        return
    papers = data if isinstance(data, list) else data.get("data", [])
    if not papers:
        print("No similar papers found.")
        return
    lines = []
    for i, p in enumerate(papers, 1):
        lines.extend([f"\n[{i}]", _fmt_paper(p)])
    _save_text(cache_path, "\n".join(lines))


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


def cmd_metadata(args):
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

    # Output cache: ./<paper_id>/paper_metadata.md with Paper, Metrics, and
    # Metadata sections. It combines the old paper, metrics, and metadata
    # commands into one structured record.
    p_paper_meta = sub.add_parser("paper_metadata", help="Get structured paper metadata")
    p_paper_meta.add_argument("id", help="arXiv ID or UUID")

    # Output cache: ./<paper_id>/overview.json plus
    # ./<paper_id>/overview_<section>.<ext>.
    # The overview section is a shorter paper walkthrough focused on the core
    # method, experiments, figures, and conclusions. The report section is a
    # longer structured research analysis covering authors, institutions,
    # landscape, motivation, methodology, findings, and impact.
    p_overview = sub.add_parser("overview", help="Get AI overview of a paper")
    p_overview.add_argument("id", help="arXiv ID or UUID")
    p_overview.add_argument(
        "--section",
        default="overview",
        choices=["abstract", "summary", "overview", "report", "citations"],
        help="Overview JSON section to print after saving or loading the raw cache",
    )

    # Output cache: ./<paper_id>/overview.md from the overview JSON report.
    # If that report is unavailable, falls back to the public markdown endpoint.
    # See tmp lookup outputs and lookup_from_overview.out.
    # Use lookup when the desired output is the fuller research-analysis report,
    # not the shorter walkthrough printed by overview --section overview.
    p_lookup = sub.add_parser("lookup", help="Get markdown report for a paper")
    p_lookup.add_argument("input", help="arXiv ID, arXiv URL, or AlphaXiv URL")

    # Output cache: ./<paper_id>/fulltext.md with extracted public paper text.
    p_fulltext = sub.add_parser("fulltext", help="Get public markdown full text of a paper")
    p_fulltext.add_argument("input", help="arXiv ID, arXiv URL, or AlphaXiv URL")

    # Output cache: ./<paper_id>/similar_limit_<n>.txt with formatted paper list.
    p_similar = sub.add_parser("similar", help="Get similar papers")
    p_similar.add_argument("id", help="arXiv ID or UUID")
    p_similar.add_argument("--limit", type=int, default=5)

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

        p_meta = sub.add_parser("metadata", help="Get paper authors, institutions, topics, GitHub")
        p_meta.add_argument("id", help="arXiv ID")

    args = parser.parse_args()

    {
        "search": cmd_search,
        "paper_metadata": cmd_paper_metadata,
        "overview": cmd_overview,
        "lookup": cmd_lookup,
        "fulltext": cmd_fulltext,
        "similar": cmd_similar,
        # "paper": cmd_paper,
        # "metrics": cmd_metrics,
        # "feed": cmd_feed,
        # "implementations": cmd_implementations,
        # "metadata": cmd_metadata,
    }[args.command](args)


if __name__ == "__main__":
    main()
