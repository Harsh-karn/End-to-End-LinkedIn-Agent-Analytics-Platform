import time
import argparse
import structlog
import uuid
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline.ingest
import pipeline.dq_checks
import pipeline.anomaly_scoring

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)

def run_pipeline():
    correlation_id = str(uuid.uuid4())
    logger = structlog.get_logger().bind(correlation_id=correlation_id)
    
    logger.info("Pipeline started")
    start_time = time.time()
    
    try:
        pipeline.ingest.logger = logger
        pipeline.dq_checks.logger = logger
        pipeline.anomaly_scoring.logger = logger
        
        from pipeline.ingest import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT MAX(run_id) FROM pipeline_run")
        prev_run = cur.fetchone()[0] or 0
        conn.close()
        
        logger.info("Starting ingestion")
        pipeline.ingest.run_ingestion()
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT MAX(run_id) FROM pipeline_run")
        run_id = cur.fetchone()[0]
        conn.close()
        
        if run_id == prev_run:
            logger.info("No new runs created in ingestion.")
            return
        
        logger.info("Starting DQ checks", run_id=run_id)
        score, status = pipeline.dq_checks.run_dq_checks(run_id)
        
        if status == 'FAIL':
            logger.error("DQ checks failed! Halting pipeline.", score=score, status=status)
            logger.error("ALERT: Pipeline halted due to DQ failure.", run_id=run_id)
            return
        elif status == 'WARN':
            logger.warning("DQ checks warned. Proceeding.", score=score)
            
        logger.info("Starting anomaly scoring")
        pipeline.anomaly_scoring.calculate_anomaly_scores()
        
        duration = time.time() - start_time
        logger.info("Pipeline completed successfully", duration_seconds=duration)
        
    except Exception as e:
        logger.error("Pipeline failed with exception", error=str(e))
        logger.error("ALERT: Pipeline failed.", correlation_id=correlation_id)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--interval", type=int, default=86400)
    args = parser.parse_args()
    
    if args.daemon:
        while True:
            run_pipeline()
            time.sleep(args.interval)
    else:
        run_pipeline()
