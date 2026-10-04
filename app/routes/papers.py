from fastapi import APIRouter, Query, HTTPException
from app.db import get_driver

router = APIRouter()


@router.get("")
def list_papers(
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    topic: str | None = None,
):
    """Paginated paper list, optionally filtered by topic name."""
    driver = get_driver()
    with driver.session() as session:
        if topic:
            query = """
                MATCH (p:Paper)-[:HAS_TOPIC]->(t:Topic {name: $topic})
                RETURN p.id AS id, p.title AS title, p.year AS year,
                       p.cited_by_count AS cited_by_count
                ORDER BY p.cited_by_count DESC
                SKIP $offset LIMIT $limit
            """
            result = session.run(query, topic=topic, offset=offset, limit=limit)
        else:
            query = """
                MATCH (p:Paper)
                RETURN p.id AS id, p.title AS title, p.year AS year,
                       p.cited_by_count AS cited_by_count
                ORDER BY p.cited_by_count DESC
                SKIP $offset LIMIT $limit
            """
            result = session.run(query, offset=offset, limit=limit)
        return [dict(r) for r in result]


@router.get("/search")
def search_papers(q: str, limit: int = Query(20, le=100)):
    """Full-text search on paper titles."""
    driver = get_driver()
    with driver.session() as session:
        query = """
            MATCH (p:Paper)
            WHERE toLower(p.title) CONTAINS toLower($q)
            RETURN p.id AS id, p.title AS title, p.year AS year,
                   p.cited_by_count AS cited_by_count
            ORDER BY p.cited_by_count DESC
            LIMIT $limit
        """
        return [dict(r) for r in session.run(query, q=q, limit=limit)]


@router.get("/{paper_id}")
def get_paper(paper_id: str):
    """Single paper with authors, topics, and references."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""
            MATCH (p:Paper {id: $id})
            OPTIONAL MATCH (a:Author)-[:AUTHORED]->(p)
            OPTIONAL MATCH (p)-[:HAS_TOPIC]->(t:Topic)
            OPTIONAL MATCH (p)-[:CITES]->(r:Paper)
            RETURN p.id AS id, p.title AS title, p.year AS year,
                   p.doi AS doi, p.cited_by_count AS cited_by_count,
                   collect(DISTINCT {id: a.id, name: a.name}) AS authors,
                   collect(DISTINCT {id: t.id, name: t.name}) AS topics,
                   collect(DISTINCT {id: r.id, title: r.title}) AS references
        """, id=paper_id).single()

        if not result:
            raise HTTPException(404, "Paper not found")
        return dict(result)