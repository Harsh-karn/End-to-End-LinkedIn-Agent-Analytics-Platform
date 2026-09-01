import os
import json
import glob
import psycopg2
from psycopg2.extras import Json
import structlog
from tenacity import retry, wait_exponential, stop_after_attempt

logger = structlog.get_logger()

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "linkedin_analytics")
DB_USER = os.getenv("POSTGRES_USER", "admin")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "admin")

def get_db_connection():
    print(f"Connecting to DB: {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER} with password: '{DB_PASS}'")
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def log_pipeline_run(conn, source, status, rows_read, rows_loaded, rows_rejected, error_summary=None, run_id=None):
    with conn.cursor() as cur:
        if run_id is None:
            cur.execute("""
                INSERT INTO pipeline_run (source, started_at, status)
                VALUES (%s, NOW(), %s) RETURNING run_id
            """, (source, status))
            conn.commit()
            return cur.fetchone()[0]
        else:
            cur.execute("""
                UPDATE pipeline_run
                SET ended_at = NOW(), status = %s, rows_read = %s, rows_loaded = %s, rows_rejected = %s, error_summary = %s
                WHERE run_id = %s
            """, (status, rows_read, rows_loaded, rows_rejected, error_summary, run_id))
            conn.commit()
            return run_id

def get_watermark(conn, source):
    with conn.cursor() as cur:
        cur.execute("SELECT last_processed_file FROM etl_watermark WHERE source = %s", (source,))
        res = cur.fetchone()
        return res[0] if res else None

def update_watermark(conn, source, file_path):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO etl_watermark (source, last_processed_ts, last_processed_file)
            VALUES (%s, NOW(), %s)
            ON CONFLICT (source) DO UPDATE SET last_processed_ts = NOW(), last_processed_file = %s
        """, (source, file_path, file_path))

def process_agent(cur, agent_data, event_ts):
    agent_id = agent_data['agent_id']
    cur.execute("SELECT agent_sk, account_age_tier, daily_invite_limit FROM dim_agent WHERE agent_id_nk = %s AND is_current = TRUE", (agent_id,))
    res = cur.fetchone()
    
    if res:
        agent_sk, current_tier, current_limit = res
        if current_tier != agent_data['tier'] or current_limit != agent_data['daily_invite_limit']:
            cur.execute("UPDATE dim_agent SET is_current = FALSE, valid_to = %s WHERE agent_sk = %s", (event_ts, agent_sk))
            cur.execute("""
                INSERT INTO dim_agent (agent_id_nk, agent_name, account_age_tier, risk_classification, daily_invite_limit, daily_message_limit, valid_from)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING agent_sk
            """, (agent_id, agent_data['name'], agent_data['tier'], agent_data['risk_classification'], agent_data['daily_invite_limit'], agent_data['daily_message_limit'], event_ts))
            return cur.fetchone()[0]
        return agent_sk
    else:
        cur.execute("""
            INSERT INTO dim_agent (agent_id_nk, agent_name, account_age_tier, risk_classification, daily_invite_limit, daily_message_limit, valid_from)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING agent_sk
        """, (agent_id, agent_data['name'], agent_data['tier'], agent_data['risk_classification'], agent_data['daily_invite_limit'], agent_data['daily_message_limit'], event_ts))
        return cur.fetchone()[0]

def process_lead(cur, lead_data):
    if not lead_data: return None
    lead_id = lead_data['lead_id']
    cur.execute("SELECT lead_sk FROM dim_lead WHERE lead_id_nk = %s", (lead_id,))
    res = cur.fetchone()
    if res: return res[0]
    
    cur.execute("""
        INSERT INTO dim_lead (lead_id_nk, segment)
        VALUES (%s, %s)
        ON CONFLICT (lead_id_nk) DO UPDATE SET segment = EXCLUDED.segment
        RETURNING lead_sk
    """, (lead_id, lead_data.get('segment')))
    return cur.fetchone()[0]

def process_campaign(cur, camp_data):
    if not camp_data: return None
    camp_id = camp_data['campaign_id']
    cur.execute("SELECT campaign_sk FROM dim_campaign WHERE campaign_id_nk = %s", (camp_id,))
    res = cur.fetchone()
    if res: return res[0]
    
    cur.execute("""
        INSERT INTO dim_campaign (campaign_id_nk, campaign_name, objective, target_segment)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (campaign_id_nk) DO UPDATE SET campaign_name = EXCLUDED.campaign_name
        RETURNING campaign_sk
    """, (camp_id, camp_data.get('name'), camp_data.get('objective'), camp_data.get('segment')))
    return cur.fetchone()[0]

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def ingest_file(file_path, run_id):
    logger.info(f"Ingesting {file_path}")
    conn = get_db_connection()
    rows_read = rows_loaded = rows_rejected = 0
    
    try:
        with open(file_path, 'r') as f:
            for line in f:
                rows_read += 1
                try:
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as e:
                        raise ValueError(f"Invalid JSON: {e}")

                    with conn.cursor() as cur:
                        agent_sk = None
                        if 'agent_data' in event:
                            agent_sk = process_agent(cur, event['agent_data'], event['timestamp'])
                        else:
                            cur.execute("SELECT agent_sk FROM dim_agent WHERE agent_id_nk = %s AND is_current = TRUE", (event.get('agent_id'),))
                            res = cur.fetchone()
                            agent_sk = res[0] if res else None
                            
                        lead_sk = None
                        camp_sk = None
                        if 'lead_data' in event:
                            lead_sk = process_lead(cur, event['lead_data'])
                            if 'campaign' in event['lead_data']:
                                camp_sk = process_campaign(cur, event['lead_data']['campaign'])
                        else:
                            if 'lead_id' in event:
                                cur.execute("SELECT lead_sk FROM dim_lead WHERE lead_id_nk = %s", (event['lead_id'],))
                                res = cur.fetchone()
                                lead_sk = res[0] if res else None
                            if 'campaign_id' in event:
                                cur.execute("SELECT campaign_sk FROM dim_campaign WHERE campaign_id_nk = %s", (event['campaign_id'],))
                                res = cur.fetchone()
                                camp_sk = res[0] if res else None
                        
                        date_sk = int(event['timestamp'][:10].replace("-", ""))
                        
                        cur.execute("""
                            INSERT INTO fact_outreach_event (
                                event_id_nk, agent_sk, lead_sk, campaign_sk, date_sk, event_type, event_ts, response_latency_hours, load_run_id
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (event_id_nk) DO UPDATE SET 
                                event_type = EXCLUDED.event_type, 
                                event_ts = EXCLUDED.event_ts
                        """, (
                            event['event_id'], agent_sk, lead_sk, camp_sk, date_sk, 
                            event['event_type'], event['timestamp'], event.get('response_latency_hours'), run_id
                        ))
                    rows_loaded += 1
                except Exception as e:
                    logger.error("Row processing failed", error=str(e))
                    with conn.cursor() as cur:
                        payload = {"raw": line}
                        if isinstance(line, str) and line.strip().startswith("{"):
                            try:
                                payload = json.loads(line)
                            except:
                                pass
                        cur.execute("INSERT INTO etl_dead_letter (run_id, payload, error_reason) VALUES (%s, %s, %s)",
                                    (run_id, Json(payload), str(e)))
                    rows_rejected += 1
        
        update_watermark(conn, "raw_events", file_path)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
        
    return rows_read, rows_loaded, rows_rejected

def run_ingestion():
    conn = get_db_connection()
    run_id = log_pipeline_run(conn, "ingest_raw_events", "running", 0, 0, 0)
    
    total_read = total_loaded = total_rejected = 0
    try:
        last_file = get_watermark(conn, "raw_events")
        all_files = sorted(glob.glob("data/raw/*/events.jsonl"))
        
        files_to_process = all_files
        if last_file and last_file in all_files:
            files_to_process = all_files[all_files.index(last_file) + 1:]
            
        for file in files_to_process:
            r, l, rej = ingest_file(file, run_id)
            total_read += r
            total_loaded += l
            total_rejected += rej
            
        log_pipeline_run(conn, "ingest_raw_events", "success", total_read, total_loaded, total_rejected, run_id=run_id)
    except Exception as e:
        logger.error("Pipeline failed", error=str(e))
        log_pipeline_run(conn, "ingest_raw_events", "failed", total_read, total_loaded, total_rejected, error_summary=str(e), run_id=run_id)
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    run_ingestion()
