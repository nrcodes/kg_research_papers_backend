import json
import os
from pathlib import Path
import certifi
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")
os.environ["SSL_CERT_FILE"] = certifi.where()
INPUT_FILE = Path("D://Projects//Knowledge_graph_research_papers//data//papers.json")
BATCH_SIZE = 500


# ---- Cypher queries ----

CONSTRAINTS = [
    "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT author_id IF NOT EXISTS FOR (a:Author) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT institution_id IF NOT EXISTS FOR (i:Institution) REQUIRE i.id IS UNIQUE",
    "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
]

LOAD_PAPERS = """
UNWIND $papers AS paper
MERGE (p:Paper {id: paper.id})
SET p.title = paper.title,
    p.year = paper.year,
    p.doi = paper.doi,
    p.cited_by_count = paper.cited_by_count
"""

LOAD_AUTHORS = """
UNWIND $papers AS paper
MATCH (p:Paper {id: paper.id})
UNWIND paper.authors AS author
MERGE (a:Author {id: author.id})
SET a.name = author.name
MERGE (a)-[:AUTHORED]->(p)
"""

LOAD_INSTITUTIONS = """
UNWIND $papers AS paper
MATCH (p:Paper {id: paper.id})
UNWIND paper.authors AS author
MATCH (a:Author {id: author.id})
WITH p, a, paper
UNWIND paper.institutions AS inst
MERGE (i:Institution {id: inst.id})
SET i.name = inst.name
MERGE (a)-[:AFFILIATED_WITH]->(i)
"""

LOAD_TOPICS = """
UNWIND $papers AS paper
MATCH (p:Paper {id: paper.id})
UNWIND paper.topics AS topic
MERGE (t:Topic {id: topic.id})
SET t.name = topic.name
MERGE (p)-[:HAS_TOPIC]->(t)
"""

LOAD_REFERENCES = """
UNWIND $papers AS paper
MATCH (p:Paper {id: paper.id})
UNWIND paper.references AS ref_id
MERGE (r:Paper {id: ref_id})
MERGE (p)-[:CITES]->(r)
"""


def chunked(items, size):
    """Yield successive chunks of `size` from `items`."""
    for i in range(0, len(items), size):
        yield items[i:i + size]


def run_query(driver, query, params=None):
    with driver.session() as session:
        session.run(query, params or {})


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"{INPUT_FILE} not found. Run fetch_papers.py first."
        )

    data = json.loads(INPUT_FILE.read_text())
    papers = data["papers"]
    print(f"Loaded {len(papers)} papers from {INPUT_FILE}")

    driver = GraphDatabase.driver(
        NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD)
    )

    try:
        driver.verify_connectivity()
        print(f"Connected to Neo4j at {NEO4J_URI}")

        # Step 1: Create constraints (must run before MERGE for speed)
        print("\nCreating constraints...")
        for c in CONSTRAINTS:
            run_query(driver, c)
        print("  Constraints ready")

        # Step 2: Load in batches
        total_batches = (len(papers) + BATCH_SIZE - 1) // BATCH_SIZE

        for i, batch in enumerate(chunked(papers, BATCH_SIZE), start=1):
            print(f"\nBatch {i}/{total_batches} ({len(batch)} papers)")

            print("  - Papers")
            run_query(driver, LOAD_PAPERS, {"papers": batch})

            print("  - Authors + AUTHORED")
            run_query(driver, LOAD_AUTHORS, {"papers": batch})

            print("  - Institutions + AFFILIATED_WITH")
            run_query(driver, LOAD_INSTITUTIONS, {"papers": batch})

            print("  - Topics + HAS_TOPIC")
            run_query(driver, LOAD_TOPICS, {"papers": batch})

            print("  - References + CITES")
            run_query(driver, LOAD_REFERENCES, {"papers": batch})

        # Step 3: Summary
        with driver.session(database=NEO4J_DATABASE) as session:
            counts = session.run("""
                MATCH (p:Paper) WITH count(p) AS papers
                MATCH (a:Author) WITH papers, count(a) AS authors
                MATCH (i:Institution) WITH papers, authors, count(i) AS insts
                MATCH (t:Topic)
                RETURN papers, authors, insts, count(t) AS topics
            """).single()

        print("\n--- Graph summary ---")
        print(f"  Papers:       {counts['papers']}")
        print(f"  Authors:      {counts['authors']}")
        print(f"  Institutions: {counts['insts']}")
        print(f"  Topics:       {counts['topics']}")

    finally:
        driver.close()


if __name__ == "__main__":
    print("URI:", NEO4J_URI)
    print("USERNAME:", NEO4J_USERNAME)
    print("DATABASE:", os.getenv("NEO4J_DATABASE"))
    main()