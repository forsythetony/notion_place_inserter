# Hello World FastAPI App

A minimal FastAPI application that returns "Hello there!" when the request includes a valid `Authorization` header matching the `secret` environment variable. Deploys to [Render](https://render.com) via Blueprint.

## Getting Started

### Prerequisites

- **Python 3.11+**
- **GitHub account** — for hosting the repository
- **Render account** — sign up at [dashboard.render.com](https://dashboard.render.com)

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/notion_place_inserter.git
   cd notion_place_inserter
   ```

2. **Create and activate a virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   make install
   # or: pip install -r requirements.txt
   ```

4. **Set the secret** (optional for local dev — defaults to `dev-secret`)
   ```bash
   export secret=your-local-secret
   ```

5. **Run the server**
   ```bash
   make run
   # or: uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
   The app will be available at `http://localhost:8000`.

### Testing Locally

With the server running in another terminal:

```bash
# Without auth — expect 401 Unauthorized
curl http://localhost:8000/

# With auth — expect 200 and {"message": "Hello there!"}
curl -H "Authorization: dev-secret" http://localhost:8000/
```

Or use the Makefile (server must be running):

```bash
make test
# With custom secret: make test SECRET=your-secret
```

### Tavern API Tests

The `http-test/` folder contains [Tavern](https://tavern.readthedocs.io/)-style API tests. With the server running:

```bash
make test-api
```

See [http-test/README.md](http-test/README.md) for configuration and usage.

### Deploying to Render

1. **Push the repository to GitHub** (if not already done)
   ```bash
   git add .
   git commit -m "Initial commit: Hello World FastAPI app"
   git push origin main
   ```

2. **Connect to Render via Blueprint**
   - Go to [dashboard.render.com](https://dashboard.render.com)
   - Click **New** → **Blueprint**
   - Connect your GitHub account and select this repository
   - Render will detect `render.yaml` and create the web service

3. **Retrieve the generated secret**
   - After the first deploy, open your service in the Render Dashboard
   - Go to the **Environment** tab
   - Find the `secret` variable — Render auto-generated it when the service was created
   - Copy the value to use in your API calls

4. **Call your deployed API**
   ```bash
   curl -H "Authorization: YOUR_RENDER_SECRET" https://hello-world-api-XXXX.onrender.com/
   ```
   Replace `YOUR_RENDER_SECRET` and the URL with your actual values.

## API Reference

| Method | Path | Header | Response |
|--------|------|--------|----------|
| GET | `/` | `Authorization: <secret>` | 200 — `{"message": "Hello there!"}` |
| GET | `/` | (missing or invalid) | 401 — Unauthorized |

## Project Structure

```
app/
  __init__.py
  main.py           # FastAPI app with auth check
http-test/
  config.tavern.yaml    # Tavern global config (base_url, secret)
  test_hello_api.tavern.yaml
  test_locations_api.tavern.yaml
  README.md
requirements.txt
render.yaml         # Render Blueprint (Infrastructure-as-Code)
pytest.ini          # Pytest/Tavern config
Makefile
README.md
```
