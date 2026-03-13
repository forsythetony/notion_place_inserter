#!/usr/bin/env python3
"""Manual verification script for p1_pr05: query job/run/events by job_id."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.env_bootstrap import bootstrap_env

bootstrap_env()

from app.integrations.supabase_config import load_supabase_config
from app.integrations.supabase_client import create_supabase_client


def main():
    job_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not job_id:
        print("Usage: python scripts/verify_pr05_manual.py <job_id>")
        print("Example: python scripts/verify_pr05_manual.py loc_9196b4ef01a3409eaa193f0f4cb95e77")
        sys.exit(1)

    config = load_supabase_config()
    client = create_supabase_client(config)

    # platform_jobs
    r = client.table(config.table_platform_jobs).select("*").eq("job_id", job_id).execute()
    jobs = r.data or []
    print("=== platform_jobs ===")
    if jobs:
        for j in jobs:
            print(f"  job_id={j.get('job_id')} status={j.get('status')} keywords={str(j.get('keywords',''))[:50]}...")
    else:
        print("  (no row found)")

    # pipeline_runs
    r = client.table(config.table_pipeline_runs).select("*").eq("job_id", job_id).execute()
    runs = r.data or []
    print("\n=== pipeline_runs ===")
    if runs:
        for rn in runs:
            print(f"  run_id={rn.get('run_id')} status={rn.get('status')} result_json={rn.get('result_json')}")
    else:
        print("  (no row found)")

    run_ids = [rn["run_id"] for rn in runs]
    if run_ids:
        # pipeline_run_events
        r = client.table(config.table_pipeline_run_events).select("*").in_("run_id", run_ids).order("created_at").execute()
        events = r.data or []
        print("\n=== pipeline_run_events ===")
        if events:
            for e in events:
                print(f"  run_id={e.get('run_id')} event_type={e.get('event_type')} payload={e.get('event_payload_json')}")
        else:
            print("  (no events found)")


if __name__ == "__main__":
    main()
