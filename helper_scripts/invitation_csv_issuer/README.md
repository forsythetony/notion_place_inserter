# Invitation CSV Issuer

Issues invitation codes and creates users by reading rows from a CSV file and calling the backend APIs.

- **issue-invitations**: Calls `POST /auth/invitations` to create invitation codes.
- **create-users**: Ensures invite exists (idempotent), then calls `POST /auth/signup` to create each user.

Both commands read from the same CSV file.

## Setup

1. Copy the template to your actual input file (gitignored):

   ```bash
   cp input_template.csv input_actual.csv
   ```

2. Edit `input_actual.csv` with your invite rows and passwords.

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## CSV format

Required headers: `userType`, `platformIssuedOn`, `issueTo`, `password`

- `userType`: One of `ADMIN`, `STANDARD`, `BETA_TESTER`
- `platformIssuedOn`: Non-empty string (e.g. `beta-signup`, `web`)
- `issueTo`: Non-empty string (e.g. email or identifier). Used as signup email for create-users.
- `password`: Non-empty string, at least 6 characters. Required for create-users; ignored by issue-invitations.

## Usage

### Issue invitations

```bash
# Dry run (validate CSV and preview payloads, no API calls)
python main.py issue-invitations --csv-path input_actual.csv --password YOUR_ADMIN_PASSWORD --dry-run

# Issue codes (requires admin credentials)
python main.py issue-invitations --csv-path input_actual.csv --password YOUR_ADMIN_PASSWORD

# With custom API base URL
python main.py issue-invitations --csv-path input_actual.csv --password YOUR_ADMIN_PASSWORD --api-base-url http://localhost:8000

# Password from env
export INVITATION_ISSUER_PASSWORD=your_admin_password
python main.py issue-invitations --csv-path input_actual.csv
```

### Create users

```bash
# Dry run (validate CSV and preview signup payloads, no API calls)
python main.py create-users --csv-path input_actual.csv --password YOUR_ADMIN_PASSWORD --dry-run

# Create users (requires admin credentials; uses CSV password column per row)
python main.py create-users --csv-path input_actual.csv --password YOUR_ADMIN_PASSWORD

# With custom API base URL
python main.py create-users --csv-path input_actual.csv --password YOUR_ADMIN_PASSWORD --api-base-url http://localhost:8000
```

## Environment

- `SUPABASE_PUBLISHABLE_KEY` — Required for auth (e.g. from `envs/local.env`)
- `SUPABASE_SECRET_KEY` — Required for profile bootstrap; creates ADMIN profile if missing (e.g. from `envs/local.env`)
- `INVITATION_ISSUER_PASSWORD` — Optional; use `--password` if not set

## Makefile

From project root:

```bash
make invite-issue-csv-help   # Show script usage
make invite-issue-csv CSV_PATH=helper_scripts/invitation_csv_issuer/input_actual.csv PASSWORD=your_password
make invite-create-users CSV_PATH=helper_scripts/invitation_csv_issuer/input_actual.csv PASSWORD=your_password
```
