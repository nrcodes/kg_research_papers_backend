from fastapi import APIRouter, Query
from app.db import get_driver

router = APIRouter()


@router.get("/{paper_id}")
def paper_neighborhood(paper_id: str, depth: int = Query(1, le=2)):
    """
    Return the neighborhood subgraph around a paper.
    depth=1 → direct neighbors, depth=2 → neighbors of neighbors.
    """
    driver = get_driver()

    # Cypher for variable-depth traversal
    query = f"""
        MATCH (center:Paper {{id: $id}})
        OPTIONAL MATCH path = (center)-[*1..{depth}]-(neighbor)
        WITH collect(path) AS paths
        UNWIND paths AS path
        UNWIND nodes(path) AS n
        WITH DISTINCT n
        RETURN
            collect(DISTINCT {{
                id: n.id,
                label: coalesce(n.title, n.name, n.id),
                group: labels(n)[0]
            }}) AS nodes
    """

    edge_query = f"""
    MATCH (center:Paper {{id: $id}})
    OPTIONAL MATCH (center)-[*1..{depth}]-(other)

    WITH center, collect(DISTINCT other) AS others
    WITH [center] + others AS all_nodes

    UNWIND all_nodes AS a
    MATCH (a)-[r]-(b)
    WHERE b IN all_nodes
      AND elementId(a) < elementId(b)

    RETURN DISTINCT
        elementId(r) AS id,
        a.id AS source,
        b.id AS target,
        type(r) AS label
"""

    with driver.session() as session:
        nodes = session.run(query, id=paper_id).single()
        links = list(session.run(edge_query, id=paper_id))

    return {
        "nodes": nodes["nodes"] if nodes else [],
        "links": [dict(e) for e in links],
    }