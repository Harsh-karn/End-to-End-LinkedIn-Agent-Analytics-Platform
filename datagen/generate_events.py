import os
import json
import random
import argparse
from datetime import datetime, timedelta
from faker import Faker
import uuid

fake = Faker()

# Tiers and Limits
TIERS = [
    {"tier": "< 1 Month", "risk": "Very High Risk", "invites": 5, "messages": 10},
    {"tier": "1 Month", "risk": "High Risk", "invites": 10, "messages": 15},
    {"tier": "2-6 Months", "risk": "Moderate Risk", "invites": 15, "messages": 25},
    {"tier": "6-12 Months", "risk": "Low Risk", "invites": 25, "messages": 40},
    {"tier": "1+ Year", "risk": "Minimal Risk", "invites": 30, "messages": 60},
]

CAMPAIGNS = [
    {"campaign_id": "CMP_001", "name": "Q3 Enterprise Outreach", "objective": "Book Demo", "segment": "Enterprise IT"},
    {"campaign_id": "CMP_002", "name": "Startup Founders", "objective": "Webinar Signups", "segment": "Startups"},
]

def generate_agents(num_agents=8):
    agents = []
    for _ in range(num_agents):
        tier = random.choice(TIERS)
        agents.append({
            "agent_id": str(uuid.uuid4()),
            "name": fake.name(),
            "tier": tier["tier"],
            "risk_classification": tier["risk"],
            "daily_invite_limit": tier["invites"],
            "daily_message_limit": tier["messages"],
            "is_anomalous": False
        })
    return agents

def generate_events(agents, num_days=60, inject_anomalies=False):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=num_days)
    
    events = []
    anomaly_labels = []
    
    if inject_anomalies and len(agents) >= 2:
        # Pick agents to be anomalous
        agents[0]["is_anomalous"] = True # Acceptance collapse
        agents[0]["anomaly_type"] = "acceptance_collapse"
        agents[1]["is_anomalous"] = True # Ghosting spike
        agents[1]["anomaly_type"] = "ghosting_spike"
        
    for agent in agents:
        leads = [{"lead_id": str(uuid.uuid4()), "campaign": random.choice(CAMPAIGNS)} for _ in range(500)]
        
        for i in range(num_days):
            current_date = start_date + timedelta(days=i)
            # determine rates based on anomalies
            accept_rate = random.uniform(0.20, 0.45)
            reply_rate = random.uniform(0.15, 0.35)
            
            if agent.get("is_anomalous"):
                if agent["anomaly_type"] == "acceptance_collapse" and i >= num_days - 10:
                    accept_rate = random.uniform(0.05, 0.10)
                    anomaly_labels.append({"date": current_date.strftime("%Y-%m-%d"), "agent_id": agent["agent_id"], "type": "acceptance_collapse"})
                if agent["anomaly_type"] == "ghosting_spike" and i >= num_days - 10:
                    reply_rate = random.uniform(0.01, 0.05)
                    anomaly_labels.append({"date": current_date.strftime("%Y-%m-%d"), "agent_id": agent["agent_id"], "type": "ghosting_spike"})

            # Generate invites
            num_invites = random.randint(1, agent["daily_invite_limit"])
            daily_leads = leads[i*agent["daily_invite_limit"]:(i+1)*agent["daily_invite_limit"]]
            
            for lead in daily_leads[:num_invites]:
                invite_id = str(uuid.uuid4())
                events.append({
                    "event_id": invite_id,
                    "event_type": "invite_sent",
                    "agent_id": agent["agent_id"],
                    "lead_id": lead["lead_id"],
                    "campaign_id": lead["campaign"]["campaign_id"],
                    "timestamp": current_date.isoformat(),
                    "agent_data": agent,
                    "lead_data": lead,
                })
                
                if random.random() < accept_rate:
                    accept_ts = current_date + timedelta(hours=random.randint(1, 48))
                    if accept_ts > end_date: continue
                    events.append({
                        "event_id": str(uuid.uuid4()),
                        "event_type": "invite_accepted",
                        "agent_id": agent["agent_id"],
                        "lead_id": lead["lead_id"],
                        "campaign_id": lead["campaign"]["campaign_id"],
                        "timestamp": accept_ts.isoformat()
                    })
                    
                    # Message sent
                    msg_ts = accept_ts + timedelta(hours=random.randint(1, 24))
                    if msg_ts > end_date: continue
                    events.append({
                        "event_id": str(uuid.uuid4()),
                        "event_type": "message_sent",
                        "agent_id": agent["agent_id"],
                        "lead_id": lead["lead_id"],
                        "campaign_id": lead["campaign"]["campaign_id"],
                        "timestamp": msg_ts.isoformat()
                    })
                    
                    if random.random() < reply_rate:
                        reply_ts = msg_ts + timedelta(hours=random.randint(1, 72))
                        if reply_ts > end_date: continue
                        events.append({
                            "event_id": str(uuid.uuid4()),
                            "event_type": "reply_received",
                            "agent_id": agent["agent_id"],
                            "lead_id": lead["lead_id"],
                            "campaign_id": lead["campaign"]["campaign_id"],
                            "timestamp": reply_ts.isoformat(),
                            "response_latency_hours": (reply_ts - msg_ts).total_seconds() / 3600.0
                        })

    return events, anomaly_labels

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inject-anomalies", action="store_true")
    args = parser.parse_args()
    
    print("Generating agents...")
    agents = generate_agents()
    
    print("Generating events...")
    events, anomaly_labels = generate_events(agents, inject_anomalies=args.inject_anomalies)
    
    # Sort events by timestamp
    events.sort(key=lambda x: x["timestamp"])
    
    # Write to files partitioned by date
    os.makedirs("data/raw", exist_ok=True)
    
    for event in events:
        date_str = event["timestamp"][:10].replace("-", "")
        dir_path = f"data/raw/{date_str}"
        os.makedirs(dir_path, exist_ok=True)
        with open(f"{dir_path}/events.jsonl", "a") as f:
            f.write(json.dumps(event) + "\n")
            
    if args.inject_anomalies:
        os.makedirs("data", exist_ok=True)
        with open("data/anomaly_labels.csv", "w") as f:
            f.write("date,agent_id,type\n")
            for label in anomaly_labels:
                f.write(f"{label['date']},{label['agent_id']},{label['type']}\n")
                
    print(f"Generated {len(events)} events.")

if __name__ == "__main__":
    main()
