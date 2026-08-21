# Data Dictionary

## fact_outreach_event
| Column | Type | Description |
|---|---|---|
| event_sk | BIGSERIAL | Surrogate key |
| event_id_nk | TEXT | Natural key, GUID |
| agent_sk | INT | FK to dim_agent |
| lead_sk | INT | FK to dim_lead |
| campaign_sk | INT | FK to dim_campaign |
| date_sk | INT | FK to dim_date (YYYYMMDD) |
| event_type | TEXT | Type of outreach event (invite_sent, invite_accepted, message_sent, reply_received, ghosted, paused, resumed) |
| event_ts | TIMESTAMPTZ | Timestamp of the event |
| response_latency_hours | NUMERIC | Hours taken for a reply (null if not a reply) |
| load_run_id | INT | FK to pipeline_run tracking data load |

## dim_agent
| Column | Type | Description |
|---|---|---|
| agent_sk | SERIAL | Surrogate key |
| agent_id_nk | TEXT | Natural key, GUID |
| agent_name | TEXT | Name of the agent persona |
| account_age_tier | TEXT | e.g. "1 Month", "2-6 Months" |
| risk_classification | TEXT | Very High Risk, Moderate Risk etc. |
| daily_invite_limit | INT | Limit per tier |
| daily_message_limit | INT | Limit per tier |
| valid_from | TIMESTAMPTZ | Start of SCD Type 2 validity |
| valid_to | TIMESTAMPTZ | End of SCD Type 2 validity (NULL if current) |
| is_current | BOOLEAN | Is this the active version of the agent record? |

## dim_lead
| Column | Type | Description |
|---|---|---|
| lead_sk | SERIAL | Surrogate key |
| lead_id_nk | TEXT | Natural key, GUID |
| segment | TEXT | E.g. "Startups", "Enterprise IT" |
| source_channel | TEXT | Source |
| first_seen_date | DATE | First activity date |

## fact_anomaly_score
| Column | Type | Description |
|---|---|---|
| id | SERIAL | PK |
| agent_sk | INT | FK to dim_agent |
| date_sk | INT | FK to dim_date |
| acceptance_zscore | NUMERIC | Modified Z-Score for Acceptance Rate |
| reply_zscore | NUMERIC | Modified Z-Score for Reply Rate |
| ghosting_zscore | NUMERIC | Modified Z-Score for Ghosting Rate |
| composite_anomaly_score | NUMERIC | Weighted sum of risk components |
| is_flagged | BOOLEAN | True if composite > 3.5 |
| capacity_recommendation | TEXT | "Maintain" or "Reduce to Floor or Pause" |
