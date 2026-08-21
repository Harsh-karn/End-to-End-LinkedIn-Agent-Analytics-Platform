# End-to-End LinkedIn Agent Analytics Platform

## Overview
This platform ingests, validates, models, and visualizes synthetic outreach data for LinkedIn automation agents. It provides data observability (Data Quality scoring) and advanced analytics (Anomaly Detection) to flag risky behaviors such as acceptance rate collapse, reply decay, and ghosting spikes.

> **Note on Data Sourcing (Part 1 Assumption):**
> This repository is built against a **synthetic outreach dataset** generated to match Polluxa's described schema. This avoids ToS/account-risk issues of connecting a real personal LinkedIn account to third-party tools, ensuring reproducibility and safety.

## Architecture
- **Data Generator:** Synthetic event stream (`datagen/generate_events.py`) mimicking the LinkedIn API.
- **Ingestion Pipeline:** Idempotent Python scripts using Pandas/Psycopg2 with a staging watermark and dead-letter tables.
- **Database:** PostgreSQL (Star Schema).
- **Data Quality:** Python-based multi-dimensional scoring evaluating completeness, uniqueness, validity, timeliness, and referential integrity.
- **Anomaly Scoring:** Python/Pandas calculating a modified z-score against a trailing 30-day MAD baseline.
- **Orchestration:** Custom Python flow script managing state and observability via `structlog`.
- **BI Layer:** Power BI Desktop connected to the Postgres warehouse.

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Power BI Desktop (for visualization)

### 1. Start the Database
```bash
docker-compose up -d db
```
This spins up PostgreSQL and automatically applies the schema (`db/schema/init.sql`).

### 2. Setup Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

### 3. Generate Synthetic Data
```bash
python datagen/generate_events.py --inject-anomalies
```
This writes labeled anomalous data to `data/raw/`.

### 4. Run the Pipeline
```bash
python pipeline/orchestration_flow.py
```
This will run the ingest, DQ, and anomaly scoring steps, logging structural JSON to standard output.

### 5. Open Power BI
Open `bi/LinkedInAgentAnalytics.pbix` (placeholder). Use the DAX measures detailed in `bi/dax_measures.md` to build the required dashboards.

## Documentation
- [Data Flow Diagram](docs/data_flow_diagram.md)
- [Data Dictionary](docs/data_dictionary.md)
- [Model Validation](docs/model_validation.md)
