# End-to-End LinkedIn Agent Analytics Platform

## Overview
This platform ingests, validates, models, and visualizes synthetic outreach data for LinkedIn automation agents. It provides data observability (Data Quality scoring) and advanced analytics (Anomaly Detection) to flag risky behaviors such as acceptance rate collapse, reply decay, and ghosting spikes.

> **Note on Data Sourcing (Part 1 Assumption):**
> This repository is built against a **synthetic outreach dataset** generated to match Polluxa's described schema. This avoids ToS/account-risk issues of connecting a real personal LinkedIn account to third-party tools, ensuring reproducibility and safety.

## Architecture
- **Data Generator:** Synthetic event stream (`datagen/generate_events.py`) mimicking the LinkedIn API.
- **Ingestion Pipeline:** Idempotent Python scripts using Pandas/Psycopg2 with a staging watermark and dead-letter tables.
- **Database:** PostgreSQL (Star Schema) running on port `15432`.
- **Data Quality:** Python-based multi-dimensional scoring evaluating completeness, uniqueness, validity, timeliness, and referential integrity.
- **Anomaly Scoring:** Python/Pandas calculating a modified z-score against a trailing 30-day MAD baseline.
- **Orchestration:** Custom Python flow script managing state and observability via `structlog`.
- **BI Layer:** Power BI Desktop dashboard (`linkedin_analytics_dashboard.pbix`) connected to the Postgres warehouse.

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Power BI Desktop (for visualization)

### 1. Start the Database
```bash
docker-compose up -d db
```
This spins up PostgreSQL on port `15432` and automatically applies the star schema (`db/schema/init.sql`).

### 2. Setup Environment
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\Activate.ps1
# On Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```
*(Make sure the `.env` file points to `POSTGRES_PORT=15432`)*

### 3. Generate Synthetic Data
```bash
python datagen/generate_events.py --inject-anomalies
```
This writes labeled anomalous data to the `data/` directory.

### 4. Run the Pipeline
```bash
python pipeline/orchestration_flow.py
```
This single orchestration script will run the ingestion, DQ checks, and anomaly scoring steps, logging everything cleanly to standard output.

### 5. View the Dashboard
Open the completed **`linkedin_analytics_dashboard.pbix`** file located in the root of this project using Power BI Desktop. The dashboard includes visuals for Core KPIs, Account Health, Risk Intelligence, and Campaign ROI.

## Documentation
- [Data Flow Diagram](docs/data_flow_diagram.md)
- [Data Dictionary](docs/data_dictionary.md)
- [Model Validation](docs/model_validation.md)
- [Evidence Pack Notes](part1_evidence/notes.md)
