# Cloudflare deployment

Worker: techzy-smartcanteen
URL: https://techzy-smartcanteen.arpitkr-in.workers.dev/
Database: techzy-smartcanteen (separate D1 database)
DB binding: DB
Worker entry: cloudflare/worker.js; upload the root index.html as a text module named index.html alongside worker.js. The schema is cloudflare/schema.sql.

Staff account setup: in Cloudflare dashboard > Workers & Pages > techzy-smartcanteen > Settings > Variables and Secrets, add a secret named STAFF_PASSWORD with a unique password of at least 12 characters. The STAFF_EMAIL variable is admin@techzy.in. Deploy the change, then sign in with that email and the chosen password. The first successful staff login creates the account; changing the secret after creation does not rotate an existing database password. Do not commit the secret.

The Cloudflare version supports in-app status notifications, not SMTP email. Payments are mock or cash at counter. No live gateway. The existing GOAXIS application and its database are separate and were not modified.

Initial release was uploaded via API from GitHub source, not connected to automatic GitHub builds. Subsequent pushes do not deploy automatically. Verify browser workflow and API before presenting publicly. The local Python server remains available for local demos.
