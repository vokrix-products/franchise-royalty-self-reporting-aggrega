
import os
import json
import time
import traceback
import requests
from datetime import datetime, timezone

import processor

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_SERVICE_KEY = os.environ['SUPABASE_SERVICE_KEY']
PRODUCT_ID = os.environ['PRODUCT_ID']

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}

def download_file(bucket, file_path):
    if file_path.startswith(bucket + "/"):
        file_path = file_path[len(bucket) + 1:]
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{file_path}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY})
    resp.raise_for_status()
    return resp.content

def upload_result(result_key, data):
    url = f"{SUPABASE_URL}/storage/v1/object/results/{result_key}"
    resp = requests.put(url, headers={"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}", "apikey": SUPABASE_SERVICE_KEY}, data=data)
    resp.raise_for_status()
    return resp

def update_job(job_id, status, output_file_path, result_summary):
    payload = {
        "status": status,
        "output_file_path": output_file_path,
        "result_summary": result_summary,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    url = f"{SUPABASE_URL}/rest/v1/jobs?id=eq.{job_id}"
    resp = requests.patch(url, headers=HEADERS, json=payload)
    resp.raise_for_status()

def notify(customer_id, success):
    title = "Processing complete" if success else "Processing failed"
    body = "Your upload has been processed successfully." if success else "There was an error processing your upload."
    notification = {
        "product_id": PRODUCT_ID,
        "customer_id": customer_id or "",
        "title": title,
        "body": body,
        "type": "success" if success else "error",
        "read": False,
    }
    url = f"{SUPABASE_URL}/rest/v1/notifications"
    try:
        resp = requests.post(url, headers=HEADERS, json=notification)
        resp.raise_for_status()
    except Exception as e:
        print(f"Notification insert failed: {e}")

def process_job(job):
    job_id = job.get("id")
    customer_id = job.get("customer_id")
    file_path = job.get("input_file_path")
    if not job_id:
        return
    if not file_path:
        update_job(job_id, "failed", None, "Missing input_file_path")
        notify(customer_id, False)
        return
    try:
        file_bytes = download_file("uploads", file_path)
        result = processor.process_file(file_bytes)

        if isinstance(result, dict) and "records" in result:
            records = result["records"]
        elif isinstance(result, list):
            records = result
        else:
            records = []

        if not records:
            records = [{
                "title": os.path.basename(file_path).rsplit(".", 1)[0],
                "status": "Submitted:good",
                "details": result if isinstance(result, dict) else {"raw": result},
                "due_date": None,
            }]

        inserted = 0
        for rec in records:
            record_payload = {
                "product_id": PRODUCT_ID,
                "customer_id": customer_id,
                "title": rec.get("title") or "Royalty Submission",
                "status": rec.get("status") or "Submitted:good",
                "details": rec.get("details") if isinstance(rec.get("details"), dict) else {"detail": rec.get("details")},
                "source_file_path": file_path,
                "due_date": rec.get("due_date"),
            }
            url = f"{SUPABASE_URL}/rest/v1/records"
            resp = requests.post(url, headers=HEADERS, json=record_payload)
            resp.raise_for_status()
            inserted += 1

        output_payload = {
            "job_id": job_id,
            "inserted_records": inserted,
            "result": result if isinstance(result, dict) else {"processed": True},
        }
        result_key = f"{job_id}.json"
        upload_result(result_key, json.dumps(output_payload).encode("utf-8"))
        update_job(job_id, "completed", result_key, f"Processed {inserted} record(s)")
        notify(customer_id, True)
    except Exception as e:
        traceback.print_exc()
        try:
            update_job(job_id, "failed", None, str(e))
        except Exception as update_err:
            print(f"Failed to update job status: {update_err}")
        notify(customer_id, False)

def poll():
    while True:
        try:
            url = f"{SUPABASE_URL}/rest/v1/jobs?status=eq.pending&job_type=eq.process_upload&product_id=eq.{PRODUCT_ID}"
            resp = requests.get(url, headers=HEADERS)
            resp.raise_for_status()
            jobs = resp.json()
            if not jobs:
                print("No pending jobs")
            for job in jobs:
                process_job(job)
        except Exception as e:
            print(f"Poll iteration error: {e}")
            traceback.print_exc()
        time.sleep(60)

if __name__ == "__main__":
    print("Poller started")
    poll()
