# Deploying on Render — Understand how deploys work

Render can [automatically deploy](https://render.com/docs/deploys#automatic-deploys) your application each time you merge a change to your codebase. You can also trigger [manual deploys](https://render.com/docs/deploys#manual-deploys), both programmatically and in the Render Dashboard.

All service types redeploy with [zero downtime](https://render.com/docs/deploys#zero-downtime-deploys) (unless they attach a persistent disk).

## Automatic deploys

As part of creating a service on Render, you link a branch of your [GitHub](https://render.com/docs/github)/ [GitLab](https://render.com/docs/gitlab)/ [Bitbucket](https://render.com/docs/bitbucket) repo (such as `main` or `production`). Whenever you push or merge a change to that branch, by default Render automatically rebuilds and redeploys your service.

Auto-deploys appear in your service's Events timeline in the Render Dashboard.

If needed, you can [skip an auto-deploy](https://render.com/docs/deploys#skipping-an-auto-deploy) for a particular commit, or even [disable auto-deploys entirely](https://render.com/docs/deploys#disabling-auto-deploys).

> Services that pull and run a [prebuilt Docker image](https://render.com/deploying-an-image) do not support auto-deploys.

### Configuring auto-deploys

Configure a service's auto-deploy behavior from its Settings page in the [Render Dashboard](https://dashboard.render.com/):

Under Auto-Deploy, select one of the following:

| Option | Description |
| --- | --- |
| On Commit | Render triggers a deploy as soon as you push or merge a change to your linked branch. This is the default behavior for a new service. |
| After CI Checks Pass | With each change to your linked branch, Render triggers a deploy only after all of your repo's CI checks pass. |
| Off | Disables auto-deploys for the service. Choose this option if you only want to trigger deploys [manually](https://render.com/docs/deploys#manual-deploys). |

#### Integrating with CI

If you set your service's [auto-deploy behavior](https://render.com/docs/deploys#configuring-auto-deploys) to After CI Checks Pass, Render waits for a new commit's CI checks to complete before triggering a deploy. If all checks pass, Render proceeds with the deploy.

For GitHub checks, Render considers a check "passed" if its conclusion is any of `success`, `neutral`, or `skipped`.

> If your repo doesn't run CI checks, use On Commit instead of After CI Checks Pass to enable auto-deploys.
>
> Render does not trigger a deploy if:
> - At least one CI check fails for the new commit
> - Zero checks are detected for the new commit

### Skipping an auto-deploy

Certain changes to your codebase might not require a new deploy, such as edits to a `README` file. In these cases, you can include a skip phrase in your Git commit message to prevent the change from triggering an auto-deploy:

```shell
git commit -m "[skip render] Update README"
```

The skip phrase is one of `[skip render]` or `[render skip]`. You can also replace `render` with one of the following:

- `cd`
- `deploy`

> For additional control over auto-deploys, configure [build filters](https://render.com/docs/monorepo-support#setting-build-filters).

## Manual deploys

You can manually trigger a Render service deploy in a variety of ways:

### Dashboard

From your service's page in the [Render Dashboard](https://dashboard.render.com/), open the Manual Deploy dropdown and select a deploy option:

| Option | Description |
| --- | --- |
| Deploy latest commit | Deploys the most recent commit on your service's linked branch. |
| Deploy a specific commit | Deploys a specific commit from your linked branch's commit history. |
| Clear build cache & deploy | Similar to Deploy latest commit, but first clears the service's build cache. |
| Restart service | Deploys the same commit that's currently deployed for the service. |

### CLI

Run the following [Render CLI](https://render.com/docs/cli) command:

```shell
render deploys create
```

This opens an interactive menu that lists the services in your workspace. Select a service to deploy.

### Deploy hook

Each Render service has a unique Deploy Hook URL available on its Settings page. You can trigger a manual deploy by sending an HTTP GET or POST request to this URL.

### API

Send a `POST` request to the Render API's [Trigger Deploy endpoint](https://api-docs.render.com/reference/create-deploy). This endpoint accepts optional body parameters for clearing the service's build cache and/or deploying a specific commit.

## Deploy steps

With each deploy, Render proceeds through the following commands for your service:

1. Build command
2. Pre-deploy command (if defined)
3. Start command

*Consumes [pipeline minutes](https://render.com/docs/build-pipeline#pipeline-minutes) while running.*

You specify these commands as part of creating your service in the [Render Dashboard](https://dashboard.render.com/). If any command fails or times out, the entire deploy fails.

Command timeouts:

| Command | Timeout |
| --- | --- |
| Build command | 120 minutes |
| Pre-deploy command | 30 minutes |
| Start command | 15 minutes |

### Build command

Performs all compilation and dependency installation that's necessary for your service to run. It usually resembles the command you use to build your project locally.

#### Example build commands for each runtime

| Runtime | Example Build Command(s) |
| --- | --- |
| Node.js | `npm install` / `pnpm install` / `bun install` / `yarn` |
| Python | `pip install -r requirements.txt` / `poetry install` / `uv sync` |
| Ruby | `bundle install` |
| Go | `go build -tags netgo -ldflags '-s -w' -o app` |
| Rust | `cargo build --release` |
| Elixir | `mix deps.get --only prod && mix compile` |

### Pre-deploy command

If defined, the pre-deploy command runs after your service's build finishes, but before that build is deployed. Recommended for tasks that should always precede a deploy but are not tied to building your code, such as:

- Uploading assets to a CDN
- Database migrations

> The pre-deploy command executes on a separate instance from your running service. Changes you make to the filesystem are not reflected in the deployed service.

### Start command

Render runs this command to start your service when it's ready to deploy.

#### Example start commands for each runtime

| Runtime | Example Start Command(s) |
| --- | --- |
| Node.js | `npm start` / `pnpm start` / `bun run start` / `yarn start` / `node index.js` |
| Python | `gunicorn your_application.wsgi` |
| Ruby | `bundle exec puma` |
| Go | `./app` |
| Rust | `cargo run --release` |
| Elixir | `mix phx.server` / `mix run --no-halt` |
| Docker | By default, Render runs the `CMD` defined in your Dockerfile. |

## Managing deploys

### Handling overlapping deploys

Only one deploy can run at a time per service. When a deploy triggers while another is in progress:

| Policy | Description |
| --- | --- |
| Wait | Allow the in-progress deploy to finish, then proceed directly to the most recently triggered deploy. |
| Override | Immediately cancel the in-progress deploy and start the new one. |

### Canceling a deploy

You can cancel an in-progress deploy in the Render Dashboard from your service's Events page.

### Restarting a service

If your service is misbehaving, you can perform a restart from the service's page in the Render Dashboard: Manual Deploy > Restart service.

On Render, a service restart is actually a special form of manual deploy—Render creates a completely new instance and swaps over to it when it's ready (zero-downtime).

### Rolling back a deploy

See [Rollbacks](https://render.com/docs/rollbacks).

## Deployment concepts

### Ephemeral filesystem

By default, Render services have an ephemeral filesystem. Any changes a running service makes to its filesystem are lost with each deploy.

To persist data across deploys:

- Attach a [persistent disk](https://render.com/docs/disks) to your service
- Create and connect to a custom datastore (MySQL, MongoDB, etc.)
- Create and connect to a Render-managed datastore (Postgres or Key Value)

### Zero-downtime deploys

Whenever you deploy a new version of your service, Render performs a sequence of steps to ensure the service stays up and available throughout the deploy process:

1. When you push up a new version, Render attempts to build it
2. If the build succeeds, Render spins up a new instance running the new version
3. For web services, your original instance continues receiving traffic while the new instance spins up
4. If the new instance spins up successfully, Render updates networking so the new instance receives all incoming traffic
5. After 60 seconds, Render sends SIGTERM to your app on the original instance for graceful shutdown
6. If your app doesn't exit within the shutdown delay (default 30 seconds), Render sends SIGKILL
7. For web services with edge caching, Render purges cache entries
8. The zero-downtime deploy is complete

> Adding a persistent disk to your service disables zero-downtime deploys.

### Graceful shutdown

Your application should define logic to perform a graceful shutdown in response to SIGTERM:

- Completing in-progress worker tasks
- Responding to remaining in-flight HTTP requests
- Terminating outbound connections
- Exiting with a zero status after cleanup

### Setting a shutdown delay

If your service needs more than 30 seconds to complete a graceful shutdown, you can specify a longer shutdown delay (up to 300 seconds) via the `maxShutdownDelaySeconds` field in your `render.yaml` or the Render API.
