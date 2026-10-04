import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

OPENALEX_BASE = "https://api.openalex.org"
EMAIL = os.getenv("OPENALEX_EMAIL", "rwnila28@gmail.com ")
HEADERS = {"User-Agent": f"mailto:{EMAIL}"}

# ---- Config ----
SEARCH_TOPIC = "large language models"
MAX_ROOT_PAPERS = 500          # how many papers to fetch for the topic
CITATION_DEPTH = 1              # how many levels of references to follow
MAX_REFS_PER_PAPER = 30         # cap references per paper
OUTPUT_FILE = Path("D://Projects//Knowledge_graph_research_papers//data//papers.json")


def fetch_works(search: str, per_page: int = 200, max_results: int = 500):
    """Fetch papers matching a search term, with cursor pagination."""
    papers = []
    cursor = "*"

    while len(papers) < max_results:
        params = {
            "search": search,
            "per-page": per_page,
            "cursor": cursor,
            "select": "id,doi,title,publication_year,authorships,"
                      "referenced_works,topics,cited_by_count",
        }
        resp = requests.get(f"{OPENALEX_BASE}/works", params=params, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            break

        papers.extend(results)
        cursor = data.get("meta", {}).get("next_cursor")
        if not cursor:
            break

        print(f"  fetched {len(papers)} papers...")
        time.sleep(0.1)

    return papers[:max_results]


def fetch_works_by_ids(ids: list[str]) -> list[dict]:
    """Fetch metadata for a list of OpenAlex work IDs (batch of 50 per call)."""
    papers = []
    batch_size = 50

    for i in range(0, len(ids), batch_size):
        batch = ids[i:i + batch_size]
        # OpenAlex filter accepts pipe-separated IDs
        filter_str = "openalex_id:" + "|".join(batch)
        params = {
            "filter": filter_str,
            "per-page": batch_size,
            "select": "id,doi,title,publication_year,authorships,"
                      "referenced_works,topics,cited_by_count",
        }
        resp = requests.get(f"{OPENALEX_BASE}/works", params=params, headers=HEADERS)
        resp.raise_for_status()
        papers.extend(resp.json().get("results", []))
        time.sleep(0.1)

    return papers


def normalize_paper(raw: dict) -> dict:
    """Convert OpenAlex work record into our flat schema."""
    authors = []
    institutions = {}

    for authorship in raw.get("authorships", []):
        author = authorship.get("author", {})
        if not author.get("id"):
            continue
        authors.append({
            "id": author["id"].split("/")[-1],
            "name": author.get("display_name", ""),
        })
        for inst in authorship.get("institutions", []):
            if inst.get("id"):
                iid = inst["id"].split("/")[-1]
                institutions[iid] = inst.get("display_name", "")

    topics = []
    for t in raw.get("topics", []):
        if t.get("id"):
            topics.append({
                "id": t["id"].split("/")[-1],
                "name": t.get("display_name", ""),
            })

    refs = [r.split("/")[-1] for r in raw.get("referenced_works", [])]

    return {
        "id": raw["id"].split("/")[-1],
        "doi": raw.get("doi"),
        "title": raw.get("title") or "",
        "year": raw.get("publication_year"),
        "cited_by_count": raw.get("cited_by_count", 0),
        "authors": authors,
        "institutions": [{"id": k, "name": v} for k, v in institutions.items()],
        "topics": topics,
        "references": refs[:MAX_REFS_PER_PAPER],
    }


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    print(f"Fetching papers for topic: {SEARCH_TOPIC}")
    root_papers = fetch_works(SEARCH_TOPIC, max_results=MAX_ROOT_PAPERS)
    print(f"Got {len(root_papers)} root papers")

    # Collect reference IDs for deeper traversal
    seen_ids = {p["id"].split("/")[-1] for p in root_papers}
    next_level_ids = set()

    for p in root_papers:
        for ref in p.get("referenced_works", []):
            rid = ref.split("/")[-1]
            if rid not in seen_ids:
                next_level_ids.add(rid)

    # Follow citations up to CITATION_DEPTH levels
    all_ids_to_fetch = set(next_level_ids)
    for depth in range(1, CITATION_DEPTH):
        print(f"Fetching {len(all_ids_to_fetch)} references at depth {depth}")
        ref_papers = fetch_works_by_ids(list(all_ids_to_fetch))
        for p in ref_papers:
            pid = p["id"].split("/")[-1]
            seen_ids.add(pid)
            for ref in p.get("referenced_works", []):
                rid = ref.split("/")[-1]
                if rid not in seen_ids:
                    next_level_ids.add(rid)
        all_ids_to_fetch = next_level_ids - seen_ids

    # Fetch the reference papers we identified
    if next_level_ids:
        print(f"Fetching {len(next_level_ids)} reference papers")
        ref_papers = fetch_works_by_ids(list(next_level_ids))
    else:
        ref_papers = []

    # Normalize and dedupe
    all_papers = {}
    for raw in root_papers + ref_papers:
        norm = normalize_paper(raw)
        all_papers[norm["id"]] = norm

    output = {"papers": list(all_papers.values())}
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))

    print(f"\nSaved {len(all_papers)} papers to {OUTPUT_FILE}")
    print(f"  - Root papers: {len(root_papers)}")
    print(f"  - Reference papers: {len(ref_papers)}")


if __name__ == "__main__":
    main()