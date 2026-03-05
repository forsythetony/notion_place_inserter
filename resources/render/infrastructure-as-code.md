# Render Blueprints (IaC) — Manage your Render infrastructure with a single YAML file

Blueprints are Render's infrastructure-as-code (IaC) model for defining, deploying, and managing multiple resources with a single YAML file.

## Example Blueprint

```yaml
# Basic example: Django web service and Postgres database
services:
  - type: web
    plan: free
    name: django-app
    runtime: python
    repo: https://github.com/render-examples/django.git
    buildCommand: './build.sh'
    startCommand: 'python -m gunicorn mysite.asgi:application -k uvicorn.workers.UvicornWorker'
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: django-app-db
          property: connectionString

databases:
  - name: django-app-db
    plan: free
```

A Blueprint acts as the single source of truth for configuring an interconnected set of services, databases, and [environment groups](https://render.com/docs/configure-environment-variables#environment-groups). Whenever you update a Blueprint, Render automatically redeploys any affected services to apply the new configuration (you can [disable this](https://render.com/docs/infrastructure-as-code#disabling-automatic-sync)).

> **Important**: Do not manage a particular service, database, or environment group with more than one Blueprint. This can result in unpredictable behavior.

## Setup

1. Create an empty YAML file in your repository (default: `render.yaml` at repo root)
2. Populate your Blueprint file with the resources you want to create. See the [Blueprint specification reference](https://render.com/docs/blueprint-spec)
3. Commit and push your changes to your Git provider
4. Open the [Render Dashboard](https://dashboard.render.com/) and click New > Blueprint
5. Click Connect for the repo containing your Blueprint
6. Specify a name for your Blueprint and which branch to link
7. Optionally specify a custom Blueprint Path (default: `render.yaml`)
8. Review the changes Render will apply
9. Click Deploy Blueprint

## Generating a Blueprint from existing services

In the Render Dashboard, select any number of your services, then click **Generate Blueprint** at the bottom of the page. This opens a page where you can download or copy the generated `render.yaml` file.

> **Important**: The generated file includes environment variable names but not their values (for security). It sets `sync: false` for each environment variable.

## Replicating a Blueprint

You can create multiple Blueprints from a single YAML file. Each Blueprint creates and manages a completely independent set of resources. Render appends a suffix to resource names to prevent collisions with existing resources.

## Managing Blueprint resources

### Adding an existing resource

You can add an existing Render resource to your Blueprint by adding its details to your Blueprint file. Include all configuration options currently set in the Dashboard. When you sync, Render applies the Blueprint configuration to the existing resource.

> Do not add an existing resource that's already managed by another Blueprint.

### Modifying a resource outside of its Blueprint

You can make changes in the Render Dashboard, but conflicting changes are overwritten the next time you sync. If you delete a Blueprint-managed resource in the Dashboard, Render recreates it on the next sync!

### Deleting a resource

Syncing a Blueprint never deletes an existing resource—even if you remove it from your Blueprint file. This is a safeguard against accidental deletions.

To delete a Blueprint-managed resource: first remove it from your Blueprint, then delete it in the Render Dashboard.

## Disabling automatic sync

By default, Render automatically updates affected resources when you push Blueprint changes to your linked branch.

To control when you sync: set **Auto Sync** to **No** on your Blueprint's Settings page. You can then manually trigger a sync by clicking **Manual Sync**.

## Supported fields and values

See the complete [Blueprint specification reference](https://render.com/docs/blueprint-spec).
