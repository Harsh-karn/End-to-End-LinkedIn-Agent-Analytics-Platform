import os
import json
import pytest
import psycopg2
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.ingest import ingest_file

@pytest.fixture
def test_db():
    if not os.getenv("POSTGRES_DB"):
        pytest.skip("Test requires POSTGRES_DB")
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )
    yield conn
    conn.close()

def test_idempotent_ingestion(test_db, tmp_path):
    # Create a dummy raw file
    data = {
        "event_id": "test-event-1",
        "event_type": "invite_sent",
        "agent_id": "agent-1",
        "lead_id": "lead-1",
        "campaign_id": "camp-1",
        "timestamp": "2023-01-01T12:00:00Z",
        "agent_data": {"agent_id": "agent-1", "name": "Test", "tier": "1 Month", "risk_classification": "High Risk", "daily_invite_limit": 10, "daily_message_limit": 15},
        "lead_data": {"lead_id": "lead-1", "campaign": {"campaign_id": "camp-1", "name": "C1", "objective": "O1", "segment": "S1"}, "segment": "S1"}
    }
    
    file_path = tmp_path / "events.jsonl"
    with open(file_path, "w") as f:
        f.write(json.dumps(data) + "\n")
        
    # Ensure cleanup before test
    with test_db.cursor() as cur:
        cur.execute("DELETE FROM fact_outreach_event WHERE event_id_nk = 'test-event-1'")
        cur.execute("INSERT INTO pipeline_run (run_id, source, started_at, status) VALUES (999, 'test', NOW(), 'running') ON CONFLICT DO NOTHING")
        cur.execute("INSERT INTO pipeline_run (run_id, source, started_at, status) VALUES (1000, 'test', NOW(), 'running') ON CONFLICT DO NOTHING")
        test_db.commit()

    # Ingest once
    r1, l1, rej1 = ingest_file(str(file_path), run_id=999)
    assert r1 == 1 and l1 == 1 and rej1 == 0
    
    with test_db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM fact_outreach_event WHERE event_id_nk = 'test-event-1'")
        count = cur.fetchone()[0]
        assert count == 1
        
    # Ingest twice
    r2, l2, rej2 = ingest_file(str(file_path), run_id=1000)
    assert r2 == 1 and l2 == 1 and rej2 == 0 
    
    with test_db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM fact_outreach_event WHERE event_id_nk = 'test-event-1'")
        count = cur.fetchone()[0]
        assert count == 1 # still 1! Idempotent.
