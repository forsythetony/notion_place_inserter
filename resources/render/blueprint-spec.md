# Blueprint YAML Reference

Every [Render Blueprint](https://render.com/docs/infrastructure-as-code) is backed by a YAML file that defines a set of interconnected services, databases, and environment groups. By default, this file is named `render.yaml` and resides in your Git repository's root directory.

## Validating Blueprints

- **IDE**: Install the [YAML extension by Red Hat](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) for VS Code/Cursor. The Blueprint spec is served from SchemaStore.org.
- **Schema URL**: `https://render.com/schema/render.yaml.json`
- **Render CLI**: `render blueprints validate render.yaml` (requires v2.7.0+)
- **Render API**: [Validate Blueprint endpoint](https://api-docs.render.com/reference/validate-blueprint)

## Root-level fields

| Field | Description |
| --- | --- |
| `services` | List of non-Postgres services (web, worker, cron, keyvalue, etc.) |
| `databases` | List of Render Postgres instances |
| `envVarGroups` | List of environment groups |
| `projects` | List of projects with environments |
| `ungrouped` | Resources that should not belong to any environment |
| `previews.generation` | Preview environment mode: `off`, `manual`, `automatic` |
| `previews.expireAfterDays` | Days to retain inactive preview environments |

## Service fields

### Essential fields

| Field | Description |
| --- | --- |
| `name` | Required. Unique service name. |
| `type` | Required. `web`, `pserv`, `worker`, `cron`, `keyvalue` |
| `runtime` | Required (except keyvalue). `node`, `python`, `elixir`, `go`, `ruby`, `rust`, `docker`, `image`, `static` |
| `plan` | Instance type: `free`, `starter`, `standard`, `pro`, `pro plus`, `pro max`, `pro ultra` |
| `buildCommand` | Required for non-Docker. Build command (e.g., `npm install`) |
| `startCommand` | Required for non-Docker. Start command (e.g., `npm start`) |
| `schedule` | Required for cron jobs. Cron expression. |
| `preDeployCommand` | Runs after build, before start (e.g., migrations) |
| `region` | `oregon`, `ohio`, `virginia`, `frankfurt`, `singapore` |
| `repo` | Git repo URL for Git-based services |
| `branch` | Branch to deploy from |
| `autoDeployTrigger` | `commit`, `checksPass`, or `off` |
| `domains` | List of custom domains |
| `healthCheckPath` | Health check endpoint path |
| `maxShutdownDelaySeconds` | Graceful shutdown delay (1-300 seconds, default 30) |

### Docker fields

| Field | Description |
| --- | --- |
| `dockerCommand` | Command to run when starting (default: Dockerfile CMD) |
| `dockerfilePath` | Path to Dockerfile (default: `./Dockerfile`) |
| `dockerContext` | Docker build context path |
| `registryCredential` | Credential for private images |
| `image` | For `runtime: image`—URL and optional creds for prebuilt image |

### Scaling

| Field | Description |
| --- | --- |
| `numInstances` | Manual scaling: number of instances |
| `scaling` | Autoscaling: `minInstances`, `maxInstances`, `targetMemoryPercent`, `targetCPUPercent` |

### Build

| Field | Description |
| --- | --- |
| `buildFilter` | `paths` and `ignoredPaths` for build triggers (glob syntax) |
| `rootDir` | Root directory within repo (for monorepos) |

### Disks

```yaml
disk:
  name: app-data      # Required
  mountPath: /opt/data # Required
  sizeGB: 5           # Default: 10
```

### Static sites

| Field | Description |
| --- | --- |
| `staticPublishPath` | Required. Path to static files (e.g., `./build`, `./dist`) |
| `headers` | HTTP response headers |
| `routes` | Redirect and rewrite rules |

### Render Key Value

| Field | Description |
| --- | --- |
| `ipAllowList` | Required. IP ranges allowed to connect |
| `maxmemoryPolicy` | Eviction policy: `allkeys-lru`, `volatile-lru`, etc. |

## Database fields

| Field | Description |
| --- | --- |
| `name` | Required. Postgres instance name. |
| `plan` | Instance type (e.g., `free`, `basic-256mb`, `pro-8gb`) |
| `region` | Deployment region |
| `databaseName` | Database name within PostgreSQL |
| `user` | PostgreSQL user name |
| `ipAllowList` | IP ranges allowed to connect |
| `diskSizeGB` | Disk size (1 or multiple of 5) |
| `readReplicas` | List of read replica names |
| `highAvailability` | `enabled: true` for HA standby |

## Environment variables

```yaml
envVars:
  - key: API_BASE_URL
    value: https://api.example.com

  - key: APP_SECRET
    generateValue: true

  - key: STRIPE_API_KEY
    sync: false

  - key: DATABASE_URL
    fromDatabase:
      name: mydatabase
      property: connectionString

  - key: MINIO_PASSWORD
    fromService:
      name: minio
      type: pserv
      envVarKey: MINIO_ROOT_PASSWORD

  - fromGroup: my-env-group
```

### Referencing values

| Property | Description |
| --- | --- |
| `host` | Service hostname on private network |
| `port` | HTTP server port |
| `hostport` | `host:port` combined |
| `connectionString` | Postgres/Key Value connection URL |
| `user`, `password`, `database` | Postgres-specific |

### Secret values

- `sync: false` — Prompt for value in Dashboard (don't hardcode secrets!)
- `generateValue: true` — Generate random base64-encoded 256-bit value

## Inbound IP rules

```yaml
ipAllowList:
  - source: 203.0.113.4/30
    description: office
  - source: 0.0.0.0/0
    description: everywhere
ipAllowList: []  # Block all external (only internal)
```

## Projects and environments

```yaml
projects:
  - name: my-project
    environments:
      - name: production
        services: [...]
        databases: [...]
        envVarGroups: [...]
        networking:
          isolation: enabled
        permissions:
          protection: enabled
```

## Environment groups

```yaml
envVarGroups:
  - name: my-env-group
    envVars:
      - key: CONCURRENCY
        value: 2
      - key: SHARED_SECRET
        generateValue: true
```

> Render does not support variable interpolation in Blueprint files. Use build/start scripts for that.
