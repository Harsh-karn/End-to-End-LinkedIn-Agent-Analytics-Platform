# Power BI DAX Measures

The following DAX measures are required to power the LinkedIn Agent Analytics Dashboard.

## Core Metrics
```dax
Total Invites = CALCULATE(COUNTROWS(fact_outreach_event), fact_outreach_event[event_type] = "invite_sent")
Total Accepts = CALCULATE(COUNTROWS(fact_outreach_event), fact_outreach_event[event_type] = "invite_accepted")
Total Messages = CALCULATE(COUNTROWS(fact_outreach_event), fact_outreach_event[event_type] = "message_sent")
Total Replies = CALCULATE(COUNTROWS(fact_outreach_event), fact_outreach_event[event_type] = "reply_received")
```

## Ratios
```dax
Acceptance Rate = DIVIDE([Total Accepts], [Total Invites], 0)
Reply Rate = DIVIDE([Total Replies], [Total Messages], 0)
Conversion Rate = DIVIDE([Total Replies], [Total Invites], 0)
```

## Agent Health & Risk
```dax
Utilization % = 
VAR CurrentInvites = [Total Invites Today]
VAR InviteLimit = MAX(dim_agent[daily_invite_limit])
RETURN DIVIDE(CurrentInvites, InviteLimit, 0)

Anomaly Score (Avg) = AVERAGE(fact_anomaly_score[composite_anomaly_score])

Flagged Agent Count = 
CALCULATE(
    DISTINCTCOUNT(fact_anomaly_score[agent_sk]),
    fact_anomaly_score[is_flagged] = TRUE()
)
```

## Data Quality
```dax
DQ Score (Latest Run) = 
CALCULATE(
    MAX(dq_result[composite_score]),
    dq_result[run_id] = MAX(pipeline_run[run_id])
)
```
