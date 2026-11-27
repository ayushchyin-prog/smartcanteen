# TECHZY — Smart Canteen | SW-10

OVERLOCK 26 hackathon project: shared SQLite-backed pre-orders, student accounts, staff dashboard, unique token, live tracking, counter display, queue ETA, daily sales and peak-hour chart. All payments are simulated or recorded at the counter; no real gateway.

## Run in VS Code (Windows)
Install Python 3.10 or newer and Git. Open the cloned repository in VS Code. In PowerShell:

```powershell
git clone https://github.com/ayushchyin-prog/smartcanteen.git
cd smartcanteen
$env:STAFF_EMAIL = "staff@example.test"
$env:STAFF_PASSWORD = Read-Host "Choose a staff password (at least 10 characters)"
python server.py
```

If already cloned, use git pull instead. Open http://localhost:8000. Register a student via Sign in > New student. Open an incognito window and sign in using the staff credentials you chose. Staff account is initialized on first start; changing the environment variable does not reset an existing password. Keep database and credentials private. The default binds to localhost; use HOST=0.0.0.0 only on a trusted demo network, with appropriate firewall settings. Python server is for local hackathon demonstrations, not internet-facing production.

## Demo flow
1. Student selects food, confirms add popup, changes cart quantity.
2. Mock payment success generates a unique token; mock failure retains cart. Cash orders remain unpaid until staff records cash.
3. Staff updates Received → Preparing → Ready → Collected. Student status and public Now Serving board poll every 3 seconds.
4. Staff manages available stock and checks daily paid sales (including simulated payments), pending cash and hourly order counts.
5. Students see in-app order notices. Optional email: set SMTP_HOST, SMTP_PORT (default 587), SMTP_FROM, SMTP_USER and SMTP_PASSWORD with an authorized SMTP provider that supports STARTTLS. Without these, email is not sent. No secrets should be committed. Use test recipients only for demonstrations.
6. Run python smoke_test.py for HTTP/API integration checks. Browser/mobile layout, SMTP delivery and live hosting require separate verification.

## Architecture
index.html — responsive HTML/CSS/JS frontend
server.py — Python HTTP API, hashed passwords and server-side sessions, role authorization, stock checks, SQLite order transactions, unique IDs and idempotency.
canteen.db — generated automatically; do not commit.
smoke_test.py — temporary-database integration tests.
Estimated wait is a simple workload estimate assuming three parallel kitchen stations, not an actual guaranteed waiting time.

## Production limitations
No deployment performed. Use a production HTTP server/framework, HTTPS, persistent backups, rate limiting, audited authentication and durable email delivery before public use. AWS is optional in SW-10. No real payment integrations. Reference GOAXIS website is not modified.
