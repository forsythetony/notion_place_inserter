# Web Services — Host dynamic web apps at a public URL

Render helps you host web apps written in your favorite language and framework: Node.js with Express, Python with Django or FastAPI, and more. Render builds and deploys your code with every push to your linked Git branch. You can also deploy a [prebuilt Docker image](https://docs.render.com/web-services#deploy-from-a-container-registry).

Every Render web service gets a unique `onrender.com` subdomain, and you can add your own [custom domains](https://docs.render.com/custom-domains). Web services can communicate with your other Render services over your private network.

> Your web service must [bind to a port](https://docs.render.com/web-services#port-binding) on host `0.0.0.0` to receive HTTP requests from the public internet. The default expected port is `10000`.

## Deploy a template

You can get started by deploying one of Render's basic app templates:

- [Laravel](https://docs.render.com/deploy-php-laravel-docker) (PHP)
- [Phoenix](https://docs.render.com/deploy-phoenix) (Elixir)
- [Rocket](https://docs.render.com/deploy-rocket-rust) (Rust)
- [Gin](https://docs.render.com/deploy-go-gin) (Go)
- [Ruby on Rails](https://docs.render.com/deploy-rails-8)
- [Django](https://docs.render.com/deploy-django) (Python)
- [Express](https://docs.render.com/deploy-node-express-app) (Node.js)

## Deploy your own code

### Deploy from GitHub / GitLab / Bitbucket

1. In the [Render Dashboard](https://dashboard.render.com/), click New > Web Service
2. Choose Build and deploy from a Git repository and click Next
3. Select your repository and click Connect
4. Provide the following details:

| Field | Description |
| --- | --- |
| Name | A name to identify your service. Your service's `onrender.com` subdomain incorporates this name. |
| Region | The geographic region where your service will run. |
| Branch | The branch of your linked Git repo to use. |
| Language | Your app's programming language. |
| Build Command | Command to build your service (e.g., `npm install`, `pip install -r requirements.txt`) |
| Start Command | Command to start your service (e.g., `npm start`, `gunicorn your_application.wsgi`) |

5. Choose an instance type (Free has [limitations](https://docs.render.com/free#free-web-services))
6. Under Advanced: set environment variables, add a persistent disk, set a health check path, etc.
7. Click Create Web Service

> Did your first deploy fail? [See common solutions.](https://docs.render.com/troubleshooting-deploys)

### Deploy from a container registry

1. In the Render Dashboard, click New > Web Service
2. Choose Deploy an existing image from a registry and click Next
3. Enter the path to your image (e.g., `docker.io/library/nginx:latest`)
4. Provide Name and Region
5. Choose an instance type
6. Click Create Web Service

## Port binding

Every Render web service must bind to a port on host `0.0.0.0` to serve HTTP requests. We recommend binding to the port defined by the `PORT` environment variable.

Example (Express):

```javascript
const express = require('express')
const app = express()
const port = process.env.PORT || 4000

app.get('/', (req, res) => {
  res.send('Hello World!')
})

app.listen(port, () => {
  console.log(`Example app listening on port ${port}`)
})
```

The default value of `PORT` is `10000` for all Render web services. You can override this in the Render Dashboard.

> If Render fails to detect a bound port, your deploy fails with an error in your logs.
>
> Reserved ports (cannot be used): `19099`, `18013`, `18012`

### Binding to multiple ports

Render forwards inbound traffic to only one HTTP port per web service. However, your service can bind to additional ports for private network traffic. Always bind your public HTTP server to the `PORT` environment variable.

## Connect to your web service

### From the public internet

Your web service is reachable at its `onrender.com` subdomain and any [custom domains](https://docs.render.com/custom-domains) you add.

Render's load balancer terminates SSL for HTTPS requests, then forwards them to your service over HTTP. HTTP requests are redirected to HTTPS first.

### From other Render services

See [Private Network](https://docs.render.com/private-network).

## Additional features

Render web services support:

- [Blueprints](https://docs.render.com/infrastructure-as-code) (Infrastructure-as-Code)
- Brotli compression
- [DDoS protection](https://docs.render.com/ddos-protection)
- HTTP/2
- [Maintenance mode](https://docs.render.com/maintenance-mode)
- [Instant rollbacks](https://docs.render.com/rollbacks)
- [Service previews](https://docs.render.com/service-previews)
- [WebSocket connections](https://docs.render.com/websocket)
- [Edge caching](https://docs.render.com/web-service-caching) for static assets
- [Persistent disks](https://docs.render.com/disks)
- Manual or automatic [scaling](https://docs.render.com/scaling)
- [Custom domains](https://docs.render.com/custom-domains) (including wildcards)
- Free, fully-managed [TLS certificates](https://docs.render.com/tls)
- [Zero-downtime deploys](https://docs.render.com/deploys#zero-downtime-deploys)
