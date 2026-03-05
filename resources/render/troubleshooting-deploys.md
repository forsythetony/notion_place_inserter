# Troubleshooting Your Deploy

Sometimes, an app that runs fine locally might fail to deploy to Render at first. When this happens, it's almost always because of differences between your local development environment and the environment that Render uses to build and run your code.

These environmental differences might include:

- The versions of your project's dependencies
- The availability of particular [tools and utilities](https://render.com/docs/native-runtimes#tools-and-utilities)
- The values of important environment variables
- The [version of your programming language](https://render.com/docs/language-support)

## 1. Check the logs

Whenever your app misbehaves, always check the logs first. Logs are available in the [Render Dashboard](https://dashboard.render.com/):

- **Runtime errors**: Open your service's Logs page to search and filter runtime logs
- **Deploy failures**: View deploy logs by clicking the word "Deploy" in your app's Events feed

Searching the log explorer for the word `error` can often direct you to a relevant log line. If the error message is unclear, try searching the web or the [Render Community](https://community.render.com/).

## 2. Ensure matching versions and configuration

Render's runtime environment might use different versions of your language or dependencies. Environment variables might also differ from your local machine.

### Runtime mismatches

- If you've selected an incorrect runtime, create a new service with the correct runtime, or change it via Render Blueprints or the API
- Select the [runtime](https://render.com/docs/language-support) that corresponds to your language (Node, Python, etc.). Use Docker runtime for Dockerfile-based projects

### Version mismatches

- Perform a fresh install locally to confirm you're using exactly the dependency versions in your repo (e.g., `package-lock.json`)
- Each language has a default version on Render; you can override it to match your local version

### Configuration mismatches

- Check logs to confirm dependencies install correctly and the start command runs successfully
- Confirm all dependencies are compatible with Linux
- Install any tools/utilities not [included by default](https://render.com/docs/native-runtimes#tools-and-utilities) as part of your build command
- Set production mode (e.g., `NODE_ENV=production`)
- [Set necessary environment variables](https://render.com/docs/configure-environment-variables) on Render (don't rely on `.env` files)

## Common errors

### Build & deploy errors

#### Missing or incorrectly referenced resources

- **Module Not Found / ModuleNotFoundError**: A referenced dependency wasn't found (check `package.json`, `requirements.txt`), or a referenced file wasn't found. On Windows, ensure file paths and names are cased correctly.

#### Language / dependency version conflicts

- `requires Python >= 3.8`: A dependency is not compatible with your Python version
- `The engine "node" is incompatible with this module`: Node.js version doesn't work with the specified module
- `SyntaxError: Unexpected token '??='`: Node.js version doesn't support the indicated operator

#### Invalid configuration

- **Misconfigured health checks**: If your health check endpoint responds unexpectedly or doesn't respond, Render cancels your deploy
- **Missing Dockerfile CMD or ENTRYPOINT**: Dockerfile must include one of these. Without both, the deploy may hang
- **Missing environment variables**: Add required variables in the Render Dashboard or `render.yaml`
- **Invalid start command**: Should match how you start your app locally (e.g., `npm start`, `gunicorn myapp:app`)
- **Invalid build command**: Should match your local build (e.g., `npm install`, `pip install -r requirements.txt`)

### Runtime errors

#### 400 Bad Request

- Django: Add your [custom domain](https://render.com/docs/custom-domains) to [`ALLOWED_HOSTS`](https://docs.djangoproject.com/en/5.0/ref/settings/#allowed-hosts)

#### 404 Not Found

- Django: Not correctly serving [static files](https://render.com/deploy-django#set-up-static-file-serving)
- Service accessing a nonexistent file (e.g., no [persistent disk](https://render.com/docs/disks), wrong path)
- Misconfigured routing, redirects, or rewrites

#### 500 Internal Server Error

- Service or database overwhelmed (too many connections, constrained CPU/RAM). Consider [scaling](https://render.com/docs/scaling)
- Database connection issues (e.g., `SSL connection has been closed unexpectedly`). Try `sslmode=require` or a [connection pool](https://render.com/docs/postgresql-connection-pooling)
- Uncaught exception causing crash or restart

#### 502 Bad Gateway

- **WORKER/SIGKILL/SIGTERM warnings**: Increase timeout values (e.g., gunicorn `timeout` parameter)
- **Node.js timeouts or "Connection reset by peer"**: Increase `server.keepAliveTimeout` and `server.headersTimeout` (e.g., to `120000`)
- **New custom domain**: May take a few minutes to an hour to propagate
- **Misconfigured host/port**: Bind to `0.0.0.0` and use the `PORT` environment variable (default `10000`)

## When to contact support

Render's support team can assist with platform-specific issues. They cannot assist with:

- Programming nuances specific to a particular library or framework
- Performance optimization
- Software design and architecture
- Debugging of application code

For these issues, consult Stack Overflow, the Render Community, or other specialized resources.
