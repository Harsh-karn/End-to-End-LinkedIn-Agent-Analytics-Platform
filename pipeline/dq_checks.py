import os
import psycopg2
import json
import structlog
from datetime import datetime, timezone

logger = structlog.get_logger()

# Environment variables
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "linkedin_analytics")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "admin")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def check_completeness(cur, run_id):
    # % of required fields non-null in fact_outreach_event
    cur.execute("""
        SELECT COUNT(*) as total,
               COUNT(event_id_nk) as id_not_null,
               COUNT(event_type) as type_not_null,
               COUNT(event_ts) as ts_not_null
        FROM fact_outreach_event
        WHERE load_run_id = %s
    """, (run_id,))
    total, id_nn, type_nn, ts_nn = cur.fetchone()
    if total == 0: return 1.0 # Vacuously true
    
    # We expect all 3 to be non-null for completeness
    completeness = (id_nn + type_nn + ts_nn) / (3.0 * total)
    return float(completeness)

def check_uniqueness(cur, run_id):
    # zero duplicate event_id_nk (which is enforced by unique constraint, so this should be 1.0)
    cur.execute("""
        SELECT COUNT(event_id_nk) as total, COUNT(DISTINCT event_id_nk) as unique_count
        FROM fact_outreach_event
        WHERE load_run_id = %s
    """, (run_id,))
    total, unique = cur.fetchone()
    if total == 0: return 1.0
    return float(unique / total)

def check_validity(cur, run_id):
    # event_type in allowed enum, event_ts not in future
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN event_type IN ('invite_sent', 'invite_accepted', 'message_sent', 'reply_received', 'ghosted', 'paused', 'resumed') THEN 1 ELSE 0 END) as valid_type,
               SUM(CASE WHEN event_ts <= NOW() THEN 1 ELSE 0 END) as valid_ts
        FROM fact_outreach_event
        WHERE load_run_id = %s
    """, (run_id,))
    total, valid_type, valid_ts = cur.fetchone()
    if total == 0: return 1.0
    # COALESCE for null sum handling
    valid_type = valid_type or 0
    valid_ts = valid_ts or 0
    return float((valid_type + valid_ts) / (2.0 * total))

def check_timeliness(cur, run_id):
    cur.execute("""
        SELECT MAX(event_ts)
        FROM fact_outreach_event
        WHERE load_run_id = %s
    """, (run_id,))
    max_ts = cur.fetchone()[0]
    if max_ts is None: return 1.0
    
    now = datetime.now(timezone.utc)
    diff_days = (now - max_ts).days
    if diff_days <= 100:
        return 1.0
    return 0.5

def check_referential_integrity(cur, run_id):
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN agent_sk IS NOT NULL THEN 1 ELSE 0 END) as valid_agent,
               SUM(CASE WHEN lead_sk IS NOT NULL THEN 1 ELSE 0 END) as valid_lead
        FROM fact_outreach_event
        WHERE load_run_id = %s
    """, (run_id,))
    total, valid_agent, valid_lead = cur.fetchone()
    if total == 0: return 1.0
    valid_agent = valid_agent or 0
    valid_lead = valid_lead or 0
    return float((valid_agent + valid_lead) / (2.0 * total))

def run_dq_checks(run_id):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            comp = check_completeness(cur, run_id)
            uniq = check_uniqueness(cur, run_id)
            vali = check_validity(cur, run_id)
            time = check_timeliness(cur, run_id)
            refe = check_referential_integrity(cur, run_id)
            
            # Weighted average
            weights = {'completeness': 0.25, 'uniqueness': 0.20, 'validity': 0.25, 'timeliness': 0.10, 'referential': 0.20}
            score = (comp * weights['completeness'] + 
                     uniq * weights['uniqueness'] + 
                     vali * weights['validity'] + 
                     time * weights['timeliness'] + 
                     refe * weights['referential'])
            
            if score >= 0.95:
                status = 'PASS'
            elif score >= 0.85:
                status = 'WARN'
            else:
                status = 'FAIL'
                
            cur.execute("""
                INSERT INTO dq_result (run_id, composite_score, status)
                VALUES (%s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET composite_score = EXCLUDED.composite_score, status = EXCLUDED.status
            """, (run_id, score, status))
            
            checks = [
                ('Completeness', 'Completeness', comp),
                ('Uniqueness', 'Uniqueness', uniq),
                ('Validity', 'Validity', vali),
                ('Timeliness', 'Timeliness', time),
                ('Referential Integrity', 'Referential', refe),
            ]
            for check_name, dim, rate in checks:
                cur.execute("""
                    INSERT INTO dq_check_detail (run_id, check_name, dimension, pass_rate, details)
                    VALUES (%s, %s, %s, %s, %s)
                """, (run_id, check_name, dim, rate, json.dumps({})))
                
            conn.commit()
            
            logger.info("DQ Checks completed", run_id=run_id, score=score, status=status)
            return score, status
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    run_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    run_dq_checks(run_id)
