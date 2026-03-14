# Invitation CSV Issuer

Issues invitation codes by reading rows from a CSV file and calling the backend `POST /auth/invitations` API.

## Setup

1. Copy the template to your actual input file (gitignored):

   ```bash
   cp input_template.csv input_actual.csv
   ```

2. Edit `input_actual.csv` with your invite rows.

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## CSV format

Required headers: `userType`, `platformIssuedOn`, `issueTo`

- `userType`: One of `ADMIN`, `STANDARD`, `BETA_TESTER`
- `platformIssuedOn`: Non-empty string (e.g. `beta-signup`, `web`)
- `issueTo`: Non-empty string (e.g. email or identifier)

## Usage

```bash
# Dry run (validate CSV and preview payloads, no API calls)
python main.py --csv-path input_actual.csv --password YOUR_PASSWORD --dry-run

# Issue codes (requires admin credentials)
python main.py --csv-path input_actual.csv --password YOUR_PASSWORD

# With custom API base URL
python main.py --csv-path input_actual.csv --password YOUR_PASSWORD --api-base-url http://localhost:8000

# Password from env
export INVITATION_ISSUER_PASSWORD=your_password
python main.py --csv-path input_actual.csv
```

## Environment

- `SUPABASE_PUBLISHABLE_KEY` — Required for auth (e.g. from `envs/local.env`)
- `INVITATION_ISSUER_PASSWORD` — Optional; use `--password` if not set

## Makefile

From project root:

```bash
make invite-issue-csv-help   # Show script usage
make invite-issue-csv CSV_PATH=helper_scripts/invitation_csv_issuer/input_actual.csv PASSWORD=your_password
```
