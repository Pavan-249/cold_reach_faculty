#!/usr/bin/env python3
"""
Simple web UI to run outreach pipeline and view tracker.
Run: python run_outreach_app.py
Then open http://127.0.0.1:5000
"""
import os
import sys
import csv
import subprocess
import threading
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

TRACKER_CSV = os.path.join("data", "outreach_tracking.csv")
TRACKER_COLUMNS = ["faculty_name", "department", "email_id", "date_email_sent", "status"]

# Optional: use Flask if available
try:
    from flask import Flask, render_template_string, request, redirect, url_for
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Outreach Pipeline</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
    h1 { color: #1a1a2e; }
    table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
    th, td { border: 1px solid #ddd; padding: 0.5rem 0.75rem; text-align: left; }
    th { background: #1a1a2e; color: #eee; }
    tr:nth-child(even) { background: #f9f9f9; }
    .btn { display: inline-block; padding: 0.6rem 1.2rem; margin: 0.25rem; border-radius: 6px;
           text-decoration: none; font-weight: 600; border: none; cursor: pointer; }
    .btn-primary { background: #4361ee; color: white; }
    .btn-primary:hover { background: #3a56d4; }
    .btn-secondary { background: #6c757d; color: white; }
    .btn-secondary:hover { background: #5a6268; }
    .msg { padding: 0.75rem; border-radius: 6px; margin: 1rem 0; }
    .msg.info { background: #e7f3ff; border: 1px solid #b3d7ff; }
    .msg.success { background: #d4edda; border: 1px solid #c3e6cb; }
    .msg.error { background: #f8d7da; border: 1px solid #f5c6cb; }
    .log { background: #1e1e2e; color: #cdd6f4; padding: 1rem; border-radius: 6px; font-family: monospace; font-size: 0.85rem; white-space: pre-wrap; max-height: 300px; overflow: auto; }
    .running { opacity: 0.8; pointer-events: none; }
  </style>
</head>
<body>
  <h1>Faculty Outreach Pipeline</h1>
  <p>Generate personalized emails, pick best resume (Data Scientist / Data Engineering), send, and track.</p>

  {% if message %}
  <div class="msg {{ msg_type }}">{{ message }}</div>
  {% endif %}

  <div style="margin: 1rem 0;">
    <form method="post" action="/run" style="display: inline;">
      <input type="hidden" name="limit" value="10">
      <button type="submit" class="btn btn-primary" name="action" value="send">Send to 10 faculty</button>
    </form>
    <form method="post" action="/run" style="display: inline;">
      <input type="hidden" name="limit" value="0">
      <button type="submit" class="btn btn-secondary" name="action" value="dry">Dry run (no send)</button>
    </form>
  </div>

  <h2>Tracker (data/outreach_tracking.csv)</h2>
  {% if rows %}
  <table>
    <thead><tr><th>Faculty</th><th>Department</th><th>Email</th><th>Date sent</th><th>Status</th></tr></thead>
    <tbody>
      {% for r in rows %}
      <tr>
        <td>{{ r.faculty_name }}</td>
        <td>{{ r.department }}</td>
        <td>{{ r.email_id }}</td>
        <td>{{ r.date_email_sent }}</td>
        <td>{{ r.status }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p>No rows yet. Run the pipeline above to add entries.</p>
  {% endif %}

  <p style="margin-top: 2rem; color: #666; font-size: 0.9rem;">
    Or from terminal: <code>./run_outreach.sh 10</code> to send to 10, <code>./run_outreach.sh</code> for dry run.
  </p>
</body>
</html>
"""

def load_tracker():
    if not os.path.isfile(TRACKER_CSV):
        return []
    rows = []
    with open(TRACKER_CSV, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows


def run_pipeline(limit=0):
    """Run daily_outreach. limit=0 means dry run."""
    cmd = [sys.executable, "ghostwriter/daily_outreach.py"]
    if limit > 0:
        cmd.extend(["--live", "--limit", str(limit)])
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=3600,
    )


if HAS_FLASK:
    app = Flask(__name__)
    run_result = None

    @app.route("/")
    def index():
        message = request.args.get("message")
        msg_type = request.args.get("msg_type", "info")
        rows = load_tracker()
        return render_template_string(INDEX_HTML, rows=rows, message=message, msg_type=msg_type)

    @app.route("/run", methods=["POST"])
    def run():
        limit = int(request.form.get("limit", 0))
        def do_run():
            global run_result
            run_result = run_pipeline(limit)
        t = threading.Thread(target=do_run)
        t.start()
        t.join(timeout=3600)
        if run_result and run_result.returncode == 0:
            msg = f"Pipeline finished. Sent to {limit} faculty." if limit else "Dry run finished."
            return redirect(url_for("index", message=msg, msg_type="success"))
        else:
            err = (run_result.stderr or run_result.stdout or "Unknown error")[:500]
            return redirect(url_for("index", message=f"Run failed: {err}", msg_type="error"))

    if __name__ == "__main__":
        print("Open http://127.0.0.1:5000")
        app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
else:
    print("Flask not installed. Run: pip install flask")
    print("Or use the shell script: ./run_outreach.sh 10")
    sys.exit(1)
