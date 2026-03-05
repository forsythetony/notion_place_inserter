# Your First Render Deploy — Run your web app in minutes

Welcome! Let's get up and running on Render.

This tutorial uses free Render resources—no payment required. All you need is a GitHub repo with the web app you want to deploy (GitLab and Bitbucket work too).

## 1. Sign up

Signing up is fast and free at [dashboard.render.com](https://dashboard.render.com/).

## 2. Choose a service type

To deploy to Render, you create a service that pulls, builds, and runs your code.

In the top-right corner of the [Render Dashboard](https://dashboard.render.com/), open the + New dropdown and select a service type.

For this tutorial, choose **Web Service** or **Static Site**:

| Service type | Description | Common frameworks |
| --- | --- | --- |
| Web Service | Choose this if your web app runs any server-side code. The app also needs to listen for HTTP requests on a port. Full-stack web apps, API servers, and mobile backends are all web services. | Express, Next.js, Fastify, Django, FastAPI, Flask, Rails, Phoenix |
| Static Site | Choose this if your web app consists entirely of static content (mostly HTML/CSS/JS). Blogs, portfolios, and documentation sets are often static sites. | Create React App, Vue.js, Hugo, Docusaurus, Next.js static exports |

You can deploy either of these service types for free on Render.

> Free web services "spin down" after 15 minutes of inactivity. They spin back up when they next receive an incoming HTTP request or new WebSocket connection.

## 3. Link your repo

After you select a service type, the service creation form appears.

1. Connect your GitHub/GitLab/Bitbucket account to Render
2. Select the repo that contains your web app and click Connect

## 4. Configure deployment

Complete the service creation form to define how Render will build and run your app.

### Web Service — Important fields

| Field | Description |
| --- | --- |
| Branch | Your service only deploys commits on the Git branch you specify (e.g., `main`). Render can automatically redeploy whenever you push changes to this branch. |
| Root Directory | For monorepos: specify the subdirectory that represents your application root. |
| Language | Your app's programming language. Use `Docker` runtime if your language isn't listed. |
| Build Command | Command to build your app and install dependencies. Examples: `npm install`, `pip install -r requirements.txt`, `bundle install` |
| Start Command | Command to start your app. Examples: `npm start`, `gunicorn your_application.wsgi`, `./bin/rails server` |
| Instance Type | Determines RAM and CPU. Choose Free to deploy for free. |
| Environment Variables | Available at both build time and runtime. Add them in the Dashboard. |

### Static Site — Important fields

| Field | Description |
| --- | --- |
| Branch | Your site only deploys commits on the branch you specify. |
| Root Directory | For monorepos: specify the subdirectory. |
| Build Command | Command to install dependencies and build static assets. Example: `npm install && npm run build` |
| Publish Directory | Directory containing static assets (e.g., `build`, `out`, `_site`) |
| Environment Variables | Available at build time. Use `REACT_APP_` or `NEXT_PUBLIC_` prefixes for substitution. |

When you're done, click **Deploy**.

## 5. Monitor your deploy

Render automatically opens a log explorer showing your deploy's progress.

- **If the deploy fails**: Status updates to Failed. Review the log feed and see [Troubleshooting Your Deploy](https://render.com/docs/troubleshooting-deploys). Push a new commit to trigger a new deploy.
- **If the deploy succeeds**: Status updates to Live. You'll see "Your service is live 🎉"

## 6. Open your app

Every Render web service and static site receives a unique `onrender.com` URL. Find this URL on your service's page in the Render Dashboard and click it to open your app.

Congratulations! You've deployed your first app on Render 🎉

## Next steps

### Connect a datastore

Render provides fully managed Postgres and Key Value instances. Both offer a Free instance type.

### Install the Render CLI

The Render CLI helps you manage services from your terminal. Trigger deploys, view logs, initiate psql sessions, and more. [Get started with the Render CLI.](https://render.com/docs/cli)

### Add a custom domain

Each service receives an `onrender.com` URL. You can also add your own custom domains. [Learn how.](https://render.com/docs/custom-domains)

### Learn about operational controls

- [Enabling maintenance mode](https://render.com/docs/maintenance-mode)
- [Rolling back a deploy](https://render.com/docs/rollbacks)
- [Analyzing service metrics](https://render.com/docs/service-metrics)
- [Scaling your instance count](https://render.com/docs/scaling)

### Explore other service types

| Service type | Description |
| --- | --- |
| [Private services](https://render.com/docs/private-services) | Run servers that aren't reachable from the public internet. |
| [Background Workers](https://render.com/docs/background-workers) | Offload long-running and computationally expensive tasks. |
| [Cron Jobs](https://render.com/docs/cronjobs) | Run periodic tasks on a schedule you define. |

Note: Free instances are not available for these service types.
