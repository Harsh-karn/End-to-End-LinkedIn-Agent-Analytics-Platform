import pandas as pd
import numpy as np
import psycopg2
import os
import structlog

logger = structlog.get_logger()

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

def calculate_anomaly_scores():
    logger.info("Starting anomaly scoring")
    conn = get_db_connection()
    
    query = """
    WITH daily_stats AS (
        SELECT 
            agent_sk,
            date_sk,
            COUNT(*) FILTER (WHERE event_type = 'invite_sent') as invites,
            COUNT(*) FILTER (WHERE event_type = 'invite_accepted') as accepts,
            COUNT(*) FILTER (WHERE event_type = 'message_sent') as messages,
            COUNT(*) FILTER (WHERE event_type = 'reply_received') as replies
        FROM fact_outreach_event
        GROUP BY agent_sk, date_sk
    )
    SELECT agent_sk, date_sk, invites, accepts, messages, replies
    FROM daily_stats
    ORDER BY agent_sk, date_sk
    """
    
    df = pd.read_sql(query, conn)
    
    if df.empty:
        logger.info("No data for anomaly scoring.")
        conn.close()
        return
        
    df['date'] = pd.to_datetime(df['date_sk'].astype(str), format='%Y%m%d')
    df = df.sort_values(['agent_sk', 'date'])
    
    results = []
    
    for agent_sk, group in df.groupby('agent_sk'):
        group = group.set_index('date').asfreq('D', fill_value=0).reset_index()
        group['agent_sk'] = agent_sk
        
        group['accept_rate'] = (group['accepts'] / group['invites'].replace(0, np.nan)).fillna(0)
        group['reply_rate'] = (group['replies'] / group['messages'].replace(0, np.nan)).fillna(0)
        group['ghosting_rate'] = 1.0 - group['reply_rate']
        
        r7_accept = group['accept_rate'].rolling(7, min_periods=1).mean()
        r7_reply = group['reply_rate'].rolling(7, min_periods=1).mean()
        r7_ghost = group['ghosting_rate'].rolling(7, min_periods=1).mean()
        
        r30_accept_med = group['accept_rate'].rolling(30, min_periods=7).median()
        r30_reply_med = group['reply_rate'].rolling(30, min_periods=7).median()
        r30_ghost_med = group['ghosting_rate'].rolling(30, min_periods=7).median()
        
        def rolling_mad(series, window=30, min_periods=7):
            return series.rolling(window, min_periods=min_periods).apply(
                lambda x: np.median(np.abs(x - np.median(x))) if len(x.dropna()) > 0 else 0, raw=False
            )
            
        r30_accept_mad = rolling_mad(group['accept_rate']).replace(0, 0.01)
        r30_reply_mad = rolling_mad(group['reply_rate']).replace(0, 0.01)
        r30_ghost_mad = rolling_mad(group['ghosting_rate']).replace(0, 0.01)
        
        z_accept = 0.6745 * (r7_accept - r30_accept_med) / r30_accept_mad
        z_reply = 0.6745 * (r7_reply - r30_reply_med) / r30_reply_mad
        z_ghost = 0.6745 * (r7_ghost - r30_ghost_med) / r30_ghost_mad
        
        risk_accept = -z_accept
        risk_reply = -z_reply
        risk_ghost = z_ghost
        
        comp_score = 0.40 * risk_accept + 0.35 * risk_reply + 0.25 * risk_ghost
        
        group['risk_accept'] = risk_accept
        group['risk_reply'] = risk_reply
        group['risk_ghost'] = risk_ghost
        group['comp_score'] = comp_score
        group['is_flagged'] = comp_score > 3.5
        
        for idx, row in group.iterrows():
            if pd.isna(row['comp_score']): continue
            date_sk = int(row['date'].strftime('%Y%m%d'))
            
            capacity = "Maintain"
            if row['is_flagged']:
                capacity = "Reduce to Floor or Pause"
                
            results.append((
                int(agent_sk), date_sk, 
                float(row['risk_accept']), float(row['risk_reply']), float(row['risk_ghost']),
                float(row['comp_score']), bool(row['is_flagged']), capacity
            ))
            
    with conn.cursor() as cur:
        # Batch insert
        from psycopg2.extras import execute_values
        execute_values(cur, """
            INSERT INTO fact_anomaly_score (
                agent_sk, date_sk, acceptance_zscore, reply_zscore, ghosting_zscore,
                composite_anomaly_score, is_flagged, capacity_recommendation
            ) VALUES %s
            ON CONFLICT (agent_sk, date_sk) DO UPDATE SET
                acceptance_zscore = EXCLUDED.acceptance_zscore,
                reply_zscore = EXCLUDED.reply_zscore,
                ghosting_zscore = EXCLUDED.ghosting_zscore,
                composite_anomaly_score = EXCLUDED.composite_anomaly_score,
                is_flagged = EXCLUDED.is_flagged,
                capacity_recommendation = EXCLUDED.capacity_recommendation
        """, results)
        
    conn.commit()
    conn.close()
    logger.info("Anomaly scoring complete", scored_days=len(results))

if __name__ == "__main__":
    calculate_anomaly_scores()
