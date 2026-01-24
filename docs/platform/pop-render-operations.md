# Pop-Render Operations Guide

## Overview

This operational guide provides comprehensive procedures for deploying, managing, monitoring, and troubleshooting the pop-render service in production environments. It covers routine operations, scaling procedures, incident response, and risk mitigation strategies.

**Target Audience:**
- DevOps Engineers
- Site Reliability Engineers (SRE)
- Platform Operations Teams
- On-call Engineers

**Prerequisites:**
- Access to Kubernetes cluster or systemd hosts
- PostgreSQL admin credentials
- Redis admin access
- MinIO admin access
- Prometheus/Grafana access

## Deployment Procedures

### Initial Deployment

#### 1. Infrastructure Prerequisites

**PostgreSQL Database:**
```bash
# Verify PostgreSQL is running
psql -h $DB_HOST -U $DB_USER -d postgres -c "SELECT version();"

# Create database
psql -h $DB_HOST -U postgres -c "CREATE DATABASE aso_render;"

# Create user with permissions
psql -h $DB_HOST -U postgres -d aso_render -c "
  CREATE USER render_user WITH PASSWORD 'secure-password';
  GRANT ALL PRIVILEGES ON DATABASE aso_render TO render_user;
"
```

**Redis Setup:**
```bash
# Verify Redis is running
redis-cli -h $REDIS_HOST ping

# Enable AOF persistence (recommended for job queue)
redis-cli -h $REDIS_HOST CONFIG SET appendonly yes
redis-cli -h $REDIS_HOST CONFIG SET appendfsync everysec
redis-cli -h $REDIS_HOST CONFIG REWRITE

# Verify AOF is enabled
redis-cli -h $REDIS_HOST CONFIG GET appendonly
```

**MinIO Bucket:**
```bash
# Using MinIO client (mc)
mc alias set myminio http://$MINIO_ENDPOINT $MINIO_ACCESS_KEY $MINIO_SECRET_KEY

# Create bucket
mc mb myminio/render-assets

# Set bucket policy (optional: for public preview URLs)
mc policy set download myminio/render-assets/renders/*/preview.jpg
```

#### 2. Database Schema Migration

**Apply schema:**
```bash
cd platform/pop-render

# Apply base schema
psql -h $DB_HOST -U render_user -d aso_render -f db/schema.sql

# Seed styles
psql -h $DB_HOST -U render_user -d aso_render -f db/seed_styles.sql

# Seed size presets
psql -h $DB_HOST -U render_user -d aso_render -f db/seed_size_presets.sql

# Verify tables
psql -h $DB_HOST -U render_user -d aso_render -c "\dt"
```

**Expected output:**
```
             List of relations
 Schema |      Name      | Type  |    Owner
--------+----------------+-------+-------------
 public | assets         | table | render_user
 public | renders        | table | render_user
 public | size_presets   | table | render_user
 public | styles         | table | render_user
```

#### 3. Docker Deployment

**Build image:**
```bash
cd platform/pop-render
docker build -t aso/pop-render:1.0.0 .
docker tag aso/pop-render:1.0.0 aso/pop-render:latest
```

**Push to registry:**
```bash
docker tag aso/pop-render:1.0.0 registry.example.com/aso/pop-render:1.0.0
docker push registry.example.com/aso/pop-render:1.0.0
```

**Create environment file:**
```bash
cat > pop-render.env <<EOF
DB_HOST=postgres.example.com
DB_PORT=5432
DB_NAME=aso_render
DB_USER=render_user
DB_PASSWORD=secure-password-123

REDIS_HOST=redis.example.com
REDIS_PORT=6379
REDIS_DB=0

MINIO_ENDPOINT=minio.example.com:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin-secret
MINIO_BUCKET=render-assets

API_PORT=8089
WORKER_COUNT=2
LOG_LEVEL=INFO
EOF
```

**Run API container:**
```bash
docker run -d \
  --name pop-render-api \
  --env-file pop-render.env \
  -p 8089:8089 \
  --restart unless-stopped \
  --log-driver json-file \
  --log-opt max-size=100m \
  --log-opt max-file=5 \
  aso/pop-render:1.0.0
```

**Run worker containers:**
```bash
# Start 4 workers for parallel processing
for i in {1..4}; do
  docker run -d \
    --name pop-render-worker-$i \
    --env-file pop-render.env \
    --restart unless-stopped \
    --log-driver json-file \
    --log-opt max-size=100m \
    --log-opt max-file=5 \
    aso/pop-render:1.0.0 \
    rq worker renders --url redis://${REDIS_HOST}:6379/0
done
```

**Verify deployment:**
```bash
# Check API health
curl http://localhost:8089/health

# Check worker logs
docker logs pop-render-worker-1

# Verify queue connection
docker exec pop-render-worker-1 rq info --url redis://${REDIS_HOST}:6379/0
```

#### 4. Kubernetes Deployment

**Create namespace:**
```bash
kubectl create namespace pop-render
```

**Create secrets:**
```bash
kubectl create secret generic pop-render-db \
  --from-literal=password=secure-password-123 \
  -n pop-render

kubectl create secret generic pop-render-minio \
  --from-literal=access-key=minioadmin \
  --from-literal=secret-key=minioadmin-secret \
  -n pop-render
```

**Apply deployment manifests:**
```bash
# API deployment
kubectl apply -f k8s/api-deployment.yaml -n pop-render

# Worker deployment
kubectl apply -f k8s/worker-deployment.yaml -n pop-render

# Service
kubectl apply -f k8s/service.yaml -n pop-render

# Ingress (if applicable)
kubectl apply -f k8s/ingress.yaml -n pop-render
```

**Example API deployment (k8s/api-deployment.yaml):**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pop-render-api
  labels:
    app: pop-render-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: pop-render-api
  template:
    metadata:
      labels:
        app: pop-render-api
    spec:
      containers:
      - name: api
        image: registry.example.com/aso/pop-render:1.0.0
        ports:
        - containerPort: 8089
        env:
        - name: DB_HOST
          value: postgres-service
        - name: DB_PORT
          value: "5432"
        - name: DB_NAME
          value: aso_render
        - name: DB_USER
          value: render_user
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: pop-render-db
              key: password
        - name: REDIS_HOST
          value: redis-service
        - name: REDIS_PORT
          value: "6379"
        - name: REDIS_DB
          value: "0"
        - name: MINIO_ENDPOINT
          value: minio-service:9000
        - name: MINIO_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: pop-render-minio
              key: access-key
        - name: MINIO_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: pop-render-minio
              key: secret-key
        - name: MINIO_BUCKET
          value: render-assets
        - name: API_PORT
          value: "8089"
        - name: WORKER_COUNT
          value: "2"
        - name: LOG_LEVEL
          value: INFO
        livenessProbe:
          httpGet:
            path: /health/liveness
            port: 8089
          initialDelaySeconds: 10
          periodSeconds: 30
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /health/readiness
            port: 8089
          initialDelaySeconds: 5
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
```

**Example worker deployment (k8s/worker-deployment.yaml):**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pop-render-worker
  labels:
    app: pop-render-worker
spec:
  replicas: 4
  selector:
    matchLabels:
      app: pop-render-worker
  template:
    metadata:
      labels:
        app: pop-render-worker
    spec:
      containers:
      - name: worker
        image: registry.example.com/aso/pop-render:1.0.0
        command: ["rq", "worker", "renders", "--url", "redis://redis-service:6379/0"]
        env:
        - name: DB_HOST
          value: postgres-service
        - name: DB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: pop-render-db
              key: password
        - name: REDIS_HOST
          value: redis-service
        - name: MINIO_ENDPOINT
          value: minio-service:9000
        - name: MINIO_ACCESS_KEY
          valueFrom:
            secretKeyRef:
              name: pop-render-minio
              key: access-key
        - name: MINIO_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: pop-render-minio
              key: secret-key
        resources:
          requests:
            memory: "512Mi"
            cpu: "1000m"
          limits:
            memory: "1Gi"
            cpu: "2000m"
```

**Verify Kubernetes deployment:**
```bash
# Check pod status
kubectl get pods -n pop-render

# Check service
kubectl get svc -n pop-render

# Test health endpoint
kubectl port-forward -n pop-render svc/pop-render-api 8089:80
curl http://localhost:8089/health

# Check worker logs
kubectl logs -n pop-render -l app=pop-render-worker --tail=50
```

### Rolling Updates

**Docker update:**
```bash
# Build new version
docker build -t aso/pop-render:1.1.0 .
docker push registry.example.com/aso/pop-render:1.1.0

# Update API (zero-downtime with new container)
docker pull registry.example.com/aso/pop-render:1.1.0
docker stop pop-render-api
docker rm pop-render-api
docker run -d \
  --name pop-render-api \
  --env-file pop-render.env \
  -p 8089:8089 \
  --restart unless-stopped \
  aso/pop-render:1.1.0

# Update workers (graceful shutdown)
for i in {1..4}; do
  docker stop pop-render-worker-$i
  docker rm pop-render-worker-$i
  docker run -d \
    --name pop-render-worker-$i \
    --env-file pop-render.env \
    --restart unless-stopped \
    aso/pop-render:1.1.0 \
    rq worker renders --url redis://${REDIS_HOST}:6379/0
done
```

**Kubernetes update:**
```bash
# Update image in deployment
kubectl set image deployment/pop-render-api \
  api=registry.example.com/aso/pop-render:1.1.0 \
  -n pop-render

kubectl set image deployment/pop-render-worker \
  worker=registry.example.com/aso/pop-render:1.1.0 \
  -n pop-render

# Monitor rollout
kubectl rollout status deployment/pop-render-api -n pop-render
kubectl rollout status deployment/pop-render-worker -n pop-render

# Rollback if needed
kubectl rollout undo deployment/pop-render-api -n pop-render
```

## Systemd Service Management

### Installing as Systemd Service

**1. Create service user:**
```bash
sudo useradd -r -s /bin/false pop-render
```

**2. Install application:**
```bash
sudo mkdir -p /opt/pop-render
sudo cp -r platform/pop-render/* /opt/pop-render/
sudo chown -R pop-render:pop-render /opt/pop-render

# Create virtual environment
cd /opt/pop-render
sudo -u pop-render python3 -m venv venv
sudo -u pop-render venv/bin/pip install -r requirements.txt
```

**3. Create environment file:**
```bash
sudo mkdir -p /etc/pop-render
sudo tee /etc/pop-render/pop-render.env > /dev/null <<EOF
DB_HOST=localhost
DB_PORT=5432
DB_NAME=aso_render
DB_USER=render_user
DB_PASSWORD=secure-password-123

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin-secret
MINIO_BUCKET=render-assets

API_PORT=8089
WORKER_COUNT=2
LOG_LEVEL=INFO
EOF

sudo chmod 600 /etc/pop-render/pop-render.env
```

**4. Create API service:**
```bash
sudo tee /etc/systemd/system/pop-render-api.service > /dev/null <<EOF
[Unit]
Description=Pop-Render API Service
After=network.target postgresql.service redis.service
Requires=postgresql.service redis.service

[Service]
Type=notify
User=pop-render
Group=pop-render
WorkingDirectory=/opt/pop-render/service
EnvironmentFile=/etc/pop-render/pop-render.env
ExecStart=/opt/pop-render/venv/bin/gunicorn \
    -w 2 \
    -b 0.0.0.0:8089 \
    --timeout 300 \
    --access-logfile /var/log/pop-render/access.log \
    --error-logfile /var/log/pop-render/error.log \
    app:app
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

**5. Create worker service template:**
```bash
sudo tee /etc/systemd/system/pop-render-worker@.service > /dev/null <<EOF
[Unit]
Description=Pop-Render RQ Worker %i
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=pop-render
Group=pop-render
WorkingDirectory=/opt/pop-render/service
EnvironmentFile=/etc/pop-render/pop-render.env
ExecStart=/opt/pop-render/venv/bin/rq worker renders \
    --url redis://\${REDIS_HOST}:\${REDIS_PORT}/\${REDIS_DB} \
    --name worker-%i \
    --worker-class rq.worker.SimpleWorker
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
```

**6. Create log directory:**
```bash
sudo mkdir -p /var/log/pop-render
sudo chown pop-render:pop-render /var/log/pop-render
```

**7. Enable and start services:**
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable API service
sudo systemctl enable pop-render-api
sudo systemctl start pop-render-api

# Enable and start 4 workers
for i in {1..4}; do
  sudo systemctl enable pop-render-worker@$i
  sudo systemctl start pop-render-worker@$i
done

# Verify status
sudo systemctl status pop-render-api
sudo systemctl status pop-render-worker@1
```

### Systemd Service Commands

**Check service status:**
```bash
sudo systemctl status pop-render-api
sudo systemctl status pop-render-worker@1
```

**Start/stop services:**
```bash
sudo systemctl start pop-render-api
sudo systemctl stop pop-render-api

sudo systemctl start pop-render-worker@1
sudo systemctl stop pop-render-worker@1
```

**Restart services:**
```bash
sudo systemctl restart pop-render-api
sudo systemctl restart pop-render-worker@{1..4}
```

**View logs:**
```bash
# Real-time logs
sudo journalctl -u pop-render-api -f

# Last 100 lines
sudo journalctl -u pop-render-api -n 100

# Logs since specific time
sudo journalctl -u pop-render-api --since "1 hour ago"

# Worker logs
sudo journalctl -u pop-render-worker@1 -f
```

**Reload configuration (no downtime):**
```bash
sudo systemctl reload pop-render-api
```

## Scaling Workers

### Horizontal Worker Scaling

Workers process rendering jobs in parallel. Scale workers based on queue depth and CPU availability.

#### Docker Scaling

**Add workers:**
```bash
# Current workers: 1-4
# Add workers 5-8

for i in {5..8}; do
  docker run -d \
    --name pop-render-worker-$i \
    --env-file pop-render.env \
    --restart unless-stopped \
    --cpus="2" \
    --memory="1g" \
    aso/pop-render:latest \
    rq worker renders --url redis://${REDIS_HOST}:6379/0
done
```

**Remove workers:**
```bash
# Gracefully stop workers 5-8
for i in {5..8}; do
  docker stop pop-render-worker-$i
  docker rm pop-render-worker-$i
done
```

#### Kubernetes Scaling

**Scale workers:**
```bash
# Scale to 8 workers
kubectl scale deployment/pop-render-worker --replicas=8 -n pop-render

# Verify scaling
kubectl get pods -n pop-render -l app=pop-render-worker
```

**Autoscaling (HPA):**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: pop-render-worker-hpa
  namespace: pop-render
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: pop-render-worker
  minReplicas: 2
  maxReplicas: 16
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: render_queue_depth
      target:
        type: AverageValue
        averageValue: "10"
```

**Apply HPA:**
```bash
kubectl apply -f k8s/worker-hpa.yaml
kubectl get hpa -n pop-render
```

#### Systemd Scaling

**Add workers:**
```bash
# Start additional workers (5-8)
for i in {5..8}; do
  sudo systemctl enable pop-render-worker@$i
  sudo systemctl start pop-render-worker@$i
done

# Verify
sudo systemctl list-units 'pop-render-worker@*'
```

**Remove workers:**
```bash
# Stop and disable workers 5-8
for i in {5..8}; do
  sudo systemctl stop pop-render-worker@$i
  sudo systemctl disable pop-render-worker@$i
done
```

### Adding CT 391 (Compute Instance)

**Scenario:** Add new compute node CT 391 to worker pool

**Preparation:**
1. Provision CT 391 with required specs:
   - CPU: 8 cores minimum
   - RAM: 16GB minimum
   - Disk: 100GB minimum
   - Network: Access to PostgreSQL, Redis, MinIO

**Docker deployment on CT 391:**
```bash
# SSH to CT 391
ssh user@ct391

# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io

# Pull image
docker pull registry.example.com/aso/pop-render:latest

# Create environment file (same as other nodes)
cat > pop-render.env <<EOF
DB_HOST=postgres.example.com
DB_PORT=5432
DB_NAME=aso_render
DB_USER=render_user
DB_PASSWORD=secure-password-123
REDIS_HOST=redis.example.com
REDIS_PORT=6379
MINIO_ENDPOINT=minio.example.com:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin-secret
EOF

# Start 8 workers on CT 391 (8 cores)
for i in {1..8}; do
  docker run -d \
    --name pop-render-worker-ct391-$i \
    --env-file pop-render.env \
    --restart unless-stopped \
    --cpus="1" \
    --memory="2g" \
    aso/pop-render:latest \
    rq worker renders --url redis://redis.example.com:6379/0 --name ct391-worker-$i
done

# Verify workers
docker ps | grep pop-render-worker
```

**Kubernetes deployment on CT 391:**
```bash
# Label CT 391 node
kubectl label nodes ct391 workload=render-worker

# Update worker deployment with node affinity
kubectl edit deployment pop-render-worker -n pop-render

# Add node affinity
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            preference:
              matchExpressions:
              - key: workload
                operator: In
                values:
                - render-worker

# Scale up to use CT 391
kubectl scale deployment/pop-render-worker --replicas=12 -n pop-render
```

**Monitoring CT 391:**
```bash
# Check worker activity
docker stats | grep pop-render-worker-ct391

# Check queue on CT 391
docker exec pop-render-worker-ct391-1 rq info --url redis://redis.example.com:6379/0

# Monitor logs
docker logs -f pop-render-worker-ct391-1
```

## Monitoring with Prometheus/Grafana

### Prometheus Configuration

**Scrape configuration (prometheus.yml):**
```yaml
scrape_configs:
  - job_name: 'pop-render-api'
    static_configs:
      - targets: ['pop-render-api:8089']
    metrics_path: '/metrics'
    scrape_interval: 30s
    scrape_timeout: 10s

  - job_name: 'pop-render-api-k8s'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - pop-render
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: pop-render-api
      - source_labels: [__meta_kubernetes_pod_ip]
        target_label: __address__
        replacement: $1:8089
```

**Verify Prometheus scraping:**
```bash
# Check targets
curl http://prometheus:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job == "pop-render-api")'

# Query metric
curl 'http://prometheus:9090/api/v1/query?query=http_requests_total' | jq
```

### Grafana Dashboard

**Import dashboard:**
1. Navigate to Grafana → Dashboards → Import
2. Upload `grafana/pop-render-dashboard.json`
3. Select Prometheus data source

**Key panels:**

#### 1. Request Rate
```promql
sum(rate(http_requests_total[5m])) by (endpoint)
```

#### 2. Error Rate
```promql
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100
```

#### 3. P95 Latency
```promql
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))
```

#### 4. Queue Depth
```promql
render_queue_depth{service="pop-render"}
```

#### 5. Renders in Progress
```promql
renders_in_progress
```

#### 6. Render Success Rate
```promql
sum(rate(render_jobs_total{status="completed"}[5m])) / sum(rate(render_jobs_total[5m])) * 100
```

#### 7. Database Connections
```promql
db_connections_active
```

#### 8. Storage Size
```promql
render_storage_bytes_total / 1024^3
```

#### 9. Worker Memory
```promql
process_resident_memory_bytes{service="pop-render"} / 1024^2
```

### Alerting Rules

**Create alert rules (pop-render-alerts.yml):**
```yaml
groups:
  - name: pop-render
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate in pop-render API"
          description: "Error rate is {{ $value | humanizePercentage }}"

      - alert: HighQueueDepth
        expr: render_queue_depth > 200
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High queue depth in pop-render"
          description: "Queue depth is {{ $value }} jobs"

      - alert: DatabaseDown
        expr: health_check_status{dependency="database"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Pop-render database is down"
          description: "Database health check failing"

      - alert: RedisDown
        expr: health_check_status{dependency="redis"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Pop-render Redis is down"
          description: "Redis health check failing"

      - alert: StorageDown
        expr: health_check_status{dependency="storage"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Pop-render storage is down"
          description: "MinIO health check failing"

      - alert: HighRenderFailureRate
        expr: sum(rate(render_jobs_total{status="failed"}[5m])) / sum(rate(render_jobs_total[5m])) > 0.10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High render failure rate"
          description: "Failure rate is {{ $value | humanizePercentage }}"

      - alert: SlowRenderPerformance
        expr: histogram_quantile(0.90, sum(rate(render_duration_seconds_bucket[5m])) by (le)) > 120
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Slow render performance"
          description: "P90 render time is {{ $value }}s"

      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes / 1024^3 > 1.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage in pop-render"
          description: "Memory usage is {{ $value }}GB"

      - alert: StorageSpaceRunningOut
        expr: render_storage_bytes_total / 1024^4 > 0.8 * 1  # 80% of 1TB
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Storage space running out"
          description: "Storage usage is {{ $value }}TB"
```

**Load alerts into Prometheus:**
```bash
# Add to prometheus.yml
rule_files:
  - /etc/prometheus/pop-render-alerts.yml

# Reload Prometheus
curl -X POST http://prometheus:9090/-/reload
```

## Troubleshooting Failed Jobs

### Identifying Failed Jobs

**Query database:**
```sql
-- Recent failed jobs
SELECT id, asset_id, style_id, error_message, created_at, completed_at
FROM renders
WHERE status = 'failed'
ORDER BY created_at DESC
LIMIT 20;

-- Failed jobs by error type
SELECT error_message, COUNT(*) as count
FROM renders
WHERE status = 'failed'
GROUP BY error_message
ORDER BY count DESC;

-- Failed jobs by style
SELECT s.name, COUNT(*) as failures
FROM renders r
JOIN styles s ON r.style_id = s.id
WHERE r.status = 'failed'
GROUP BY s.name;
```

**Check RQ failed queue:**
```bash
# Docker
docker exec pop-render-worker-1 rq info --url redis://${REDIS_HOST}:6379/0

# Direct Redis
redis-cli -h ${REDIS_HOST} LLEN rq:queue:failed

# List failed jobs
redis-cli -h ${REDIS_HOST} LRANGE rq:queue:failed 0 10
```

### Common Failure Scenarios

#### 1. Out of Memory (OOM)

**Symptoms:**
- Worker pod/container killed
- Error message: "Killed" or "OOMKilled"
- Large image dimensions (>8000px)

**Diagnosis:**
```bash
# Check worker memory usage
docker stats pop-render-worker-1

# Check Kubernetes events
kubectl describe pod pop-render-worker-xxx -n pop-render | grep -i oom
```

**Resolution:**
```bash
# Increase worker memory limits
# Docker:
docker run -d --memory="2g" ...

# Kubernetes:
kubectl edit deployment pop-render-worker -n pop-render
# Update resources.limits.memory to 2Gi

# OR: Scale down images before processing (add to pipeline)
# Edit service/pipelines/base.py
def preprocess_image(self, image, max_dimension=8000):
    if max(image.size) > max_dimension:
        scale = max_dimension / max(image.size)
        new_size = tuple(int(dim * scale) for dim in image.size)
        image = image.resize(new_size, Image.LANCZOS)
    return image
```

#### 2. MinIO Connection Timeout

**Symptoms:**
- Error message: "Connection timeout" or "Unable to connect to MinIO"
- Long upload/download times

**Diagnosis:**
```bash
# Test MinIO connectivity from worker
docker exec pop-render-worker-1 curl -v http://${MINIO_ENDPOINT}/minio/health/live

# Check MinIO logs
docker logs minio

# Check network latency
docker exec pop-render-worker-1 ping -c 5 ${MINIO_ENDPOINT}
```

**Resolution:**
```bash
# Increase timeout in service/storage.py
config=BotoConfig(
    connect_timeout=30,  # Increase from 10
    read_timeout=120,    # Increase from 30
)

# OR: Add retry logic with exponential backoff
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=4, max=60)
)
def upload_file_with_retry(self, file_path, object_key):
    return self.upload_file(file_path, object_key)
```

#### 3. Database Connection Pool Exhausted

**Symptoms:**
- Error message: "OperationalError: connection pool exhausted"
- Slow job processing
- High db_connections_active metric

**Diagnosis:**
```sql
-- Check active connections
SELECT count(*) FROM pg_stat_activity WHERE datname = 'aso_render';

-- Check long-running queries
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - pg_stat_activity.query_start > interval '5 minutes';
```

**Resolution:**
```bash
# Increase connection pool size
# Edit service/database.py
pool = ThreadedConnectionPool(
    min_connections=2,
    max_connections=20,  # Increase from 10
    ...
)

# OR: Kill long-running queries
psql -h $DB_HOST -U $DB_USER -d aso_render -c "SELECT pg_terminate_backend(12345);"
```

#### 4. Corrupted Image File

**Symptoms:**
- Error message: "Cannot identify image file" or "Truncated image"
- Specific asset_id consistently fails

**Diagnosis:**
```bash
# Download problematic asset from MinIO
mc cp myminio/render-assets/uploads/{asset_id}/{filename} /tmp/

# Verify image
file /tmp/{filename}
identify /tmp/{filename}  # ImageMagick

# Try opening with PIL
python3 -c "from PIL import Image; Image.open('/tmp/{filename}').verify()"
```

**Resolution:**
```bash
# Mark render as failed with descriptive error
UPDATE renders
SET status='failed', error_message='Corrupted source image'
WHERE id='{render_id}';

# Notify user to re-upload asset

# OR: Add image validation during upload in routes/renders.py
try:
    image = Image.open(file)
    image.verify()
    file.seek(0)  # Reset file pointer after verify
except Exception as e:
    return jsonify({'error': 'Invalid or corrupted image file'}), 400
```

### Requeuing Failed Jobs

**Requeue single job:**
```bash
# Get render_id from failed job
render_id="3fa85f64-5717-4562-b3fc-2c963f66afa6"

# Reset status in DB
psql -h $DB_HOST -U $DB_USER -d aso_render -c "
UPDATE renders
SET status='queued', error_message=NULL, started_at=NULL, completed_at=NULL
WHERE id='${render_id}';
"

# Re-enqueue in Redis (via Python script)
python3 <<EOF
from service.queue import queue_manager
from service.database import get_render
queue_manager.initialize()
render = get_render('${render_id}')
queue_manager.enqueue_render(
    render['id'],
    render['asset_id'],
    render['style_id'],
    render['size_preset_id']
)
EOF
```

**Bulk requeue failed jobs:**
```sql
-- Reset all failed jobs from last hour
UPDATE renders
SET status='queued', error_message=NULL, started_at=NULL, completed_at=NULL
WHERE status='failed' AND created_at > NOW() - INTERVAL '1 hour';
```

```python
# Re-enqueue script (requeue_failed.py)
from service.queue import queue_manager
from service.database import db_pool

queue_manager.initialize()

with db_pool.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, asset_id, style_id, size_preset_id
            FROM renders
            WHERE status='queued' AND started_at IS NULL
        """)
        renders = cur.fetchall()

        for render in renders:
            queue_manager.enqueue_render(
                render['id'],
                render['asset_id'],
                render['style_id'],
                render['size_preset_id']
            )
            print(f"Requeued render {render['id']}")

print(f"Requeued {len(renders)} jobs")
```

## Redis AOF Recovery

Redis Append-Only File (AOF) provides persistence for the job queue.

### Enabling AOF

```bash
# Enable AOF
redis-cli -h $REDIS_HOST CONFIG SET appendonly yes
redis-cli -h $REDIS_HOST CONFIG SET appendfsync everysec
redis-cli -h $REDIS_HOST CONFIG REWRITE

# Verify AOF is enabled
redis-cli -h $REDIS_HOST INFO persistence | grep aof_enabled
```

### AOF Corruption Recovery

**Symptoms:**
- Redis fails to start
- Error: "Bad file format reading the append only file"

**Recovery procedure:**
```bash
# Stop Redis
sudo systemctl stop redis

# Backup corrupted AOF
cp /var/lib/redis/appendonly.aof /var/lib/redis/appendonly.aof.backup

# Run AOF repair tool
redis-check-aof --fix /var/lib/redis/appendonly.aof

# Output will show:
# "AOF analyzed, n errors found"
# "This will shrink the AOF from X bytes, with Y bytes, to Z bytes"
# "Continue? [y/N]"

# Confirm with 'y'

# Start Redis
sudo systemctl start redis

# Verify Redis is running
redis-cli -h $REDIS_HOST PING
```

**If repair fails:**
```bash
# Start Redis without AOF
redis-server --appendonly no

# Flush corrupted data (CAUTION: loses queue data)
redis-cli -h $REDIS_HOST FLUSHDB

# Re-enable AOF
redis-cli -h $REDIS_HOST CONFIG SET appendonly yes
redis-cli -h $REDIS_HOST CONFIG REWRITE

# Requeue all pending jobs from database
python3 requeue_failed.py
```

### AOF Rewrite

AOF grows over time. Periodically rewrite to compact.

```bash
# Trigger manual rewrite
redis-cli -h $REDIS_HOST BGREWRITEAOF

# Check rewrite status
redis-cli -h $REDIS_HOST INFO persistence | grep aof_rewrite

# Configure automatic rewrite
redis-cli -h $REDIS_HOST CONFIG SET auto-aof-rewrite-percentage 100
redis-cli -h $REDIS_HOST CONFIG SET auto-aof-rewrite-min-size 64mb
redis-cli -h $REDIS_HOST CONFIG REWRITE
```

## MinIO Storage Cleanup

### Identifying Orphaned Objects

Objects may become orphaned if render jobs fail or are deleted.

**List all render outputs:**
```bash
mc ls --recursive myminio/render-assets/renders/ > /tmp/minio_renders.txt
```

**Find renders with no DB record:**
```python
# cleanup_orphaned.py
import subprocess
import psycopg2

# Get all render IDs from MinIO
minio_output = subprocess.check_output(['mc', 'ls', '--recursive', 'myminio/render-assets/renders/']).decode()
minio_render_ids = set()
for line in minio_output.split('\n'):
    if '/renders/' in line:
        render_id = line.split('/renders/')[1].split('/')[0]
        minio_render_ids.add(render_id)

# Get all render IDs from database
conn = psycopg2.connect(
    host=DB_HOST,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)
cur = conn.cursor()
cur.execute("SELECT id FROM renders")
db_render_ids = set(row[0] for row in cur.fetchall())

# Find orphaned renders
orphaned = minio_render_ids - db_render_ids
print(f"Found {len(orphaned)} orphaned renders")

for render_id in orphaned:
    print(f"Orphaned: {render_id}")
    # Optionally delete
    # subprocess.call(['mc', 'rm', '--recursive', f'myminio/render-assets/renders/{render_id}/'])

cur.close()
conn.close()
```

### Deleting Old Renders

**Delete renders older than 90 days:**
```python
# cleanup_old_renders.py
import subprocess
from datetime import datetime, timedelta
import psycopg2

conn = psycopg2.connect(...)
cur = conn.cursor()

cutoff_date = datetime.now() - timedelta(days=90)

# Find old completed renders
cur.execute("""
    SELECT id, output_minio_key, preview_minio_key
    FROM renders
    WHERE status='completed' AND completed_at < %s
""", (cutoff_date,))

old_renders = cur.fetchall()

for render in old_renders:
    render_id, output_key, preview_key = render

    # Delete from MinIO
    if output_key:
        subprocess.call(['mc', 'rm', f'myminio/render-assets/{output_key}'])
    if preview_key:
        subprocess.call(['mc', 'rm', f'myminio/render-assets/{preview_key}'])

    # Mark as archived in DB (or delete)
    cur.execute("UPDATE renders SET status='archived' WHERE id=%s", (render_id,))

conn.commit()
print(f"Archived {len(old_renders)} old renders")
```

### Storage Quota Management

**Check bucket size:**
```bash
mc du myminio/render-assets
```

**Set lifecycle policy (auto-delete after 90 days):**
```bash
# Create lifecycle config
cat > lifecycle.json <<EOF
{
  "Rules": [
    {
      "Expiration": {
        "Days": 90
      },
      "ID": "DeleteOldRenders",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "renders/"
      }
    }
  ]
}
EOF

# Apply lifecycle
mc ilm import myminio/render-assets < lifecycle.json

# Verify
mc ilm ls myminio/render-assets
```

## Database Migration Procedure

### Schema Changes

**Example: Add new column to renders table**

**1. Create migration script:**
```sql
-- migrations/002_add_render_metadata.sql
BEGIN;

-- Add new column
ALTER TABLE renders ADD COLUMN render_metadata JSONB DEFAULT '{}';

-- Create index
CREATE INDEX idx_renders_metadata ON renders USING gin(render_metadata);

-- Update migration version
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO schema_migrations (version) VALUES (2);

COMMIT;
```

**2. Test migration on dev database:**
```bash
psql -h dev-db -U render_user -d aso_render -f migrations/002_add_render_metadata.sql
```

**3. Apply to production:**
```bash
# Backup database first
pg_dump -h $DB_HOST -U $DB_USER -d aso_render -F c -f backup_$(date +%Y%m%d).dump

# Apply migration
psql -h $DB_HOST -U $DB_USER -d aso_render -f migrations/002_add_render_metadata.sql

# Verify
psql -h $DB_HOST -U $DB_USER -d aso_render -c "\d renders"
```

### Rollback Procedure

**Create rollback script:**
```sql
-- migrations/002_add_render_metadata_rollback.sql
BEGIN;

-- Remove column
ALTER TABLE renders DROP COLUMN render_metadata;

-- Remove index (if separate)
DROP INDEX IF EXISTS idx_renders_metadata;

-- Revert migration version
DELETE FROM schema_migrations WHERE version = 2;

COMMIT;
```

**Execute rollback:**
```bash
psql -h $DB_HOST -U $DB_USER -d aso_render -f migrations/002_add_render_metadata_rollback.sql
```

### Data Migration

**Example: Migrate algorithm_config from styles to renders**

```sql
BEGIN;

-- Add column
ALTER TABLE renders ADD COLUMN algorithm_config_snapshot JSONB;

-- Populate from styles
UPDATE renders r
SET algorithm_config_snapshot = s.algorithm_config
FROM styles s
WHERE r.style_id = s.id;

COMMIT;
```

## Operational Runbook

### Restarting Workers

**When to restart:**
- Memory leaks (gradual memory increase)
- Worker becomes unresponsive
- After code deployment
- Configuration changes

**Docker:**
```bash
# Graceful restart (waits for current job to complete)
docker stop --time=300 pop-render-worker-1  # 5-minute grace period
docker start pop-render-worker-1

# Force restart (loses current job)
docker restart pop-render-worker-1

# Rolling restart (all workers)
for i in {1..4}; do
  docker restart pop-render-worker-$i
  sleep 30  # Wait before restarting next
done
```

**Kubernetes:**
```bash
# Rolling restart
kubectl rollout restart deployment/pop-render-worker -n pop-render

# Delete specific pod (will be recreated)
kubectl delete pod pop-render-worker-xxx -n pop-render
```

**Systemd:**
```bash
# Restart single worker
sudo systemctl restart pop-render-worker@1

# Restart all workers
sudo systemctl restart pop-render-worker@{1..4}
```

### Clearing Failed Queue

**When to clear:**
- After fixing bug causing widespread failures
- Failed jobs are no longer relevant
- Queue cleanup during maintenance

**Procedure:**
```bash
# View failed queue
redis-cli -h $REDIS_HOST LRANGE rq:queue:failed 0 -1

# Count failed jobs
redis-cli -h $REDIS_HOST LLEN rq:queue:failed

# Clear failed queue (CAUTION: irreversible)
redis-cli -h $REDIS_HOST DEL rq:queue:failed

# OR: Move failed jobs to separate queue for analysis
redis-cli -h $REDIS_HOST RENAME rq:queue:failed rq:queue:failed:archive:$(date +%Y%m%d)
```

**Update database:**
```sql
-- Mark failed jobs as archived
UPDATE renders
SET metadata = jsonb_set(COALESCE(metadata, '{}'), '{archived}', 'true', true)
WHERE status='failed' AND completed_at < NOW() - INTERVAL '7 days';
```

### Debugging Stuck Jobs

**Symptoms:**
- Job status remains "started" for hours
- Worker appears to be running but not progressing

**Investigation:**
```bash
# 1. Check worker process
docker exec pop-render-worker-1 ps aux | grep rq

# 2. Check worker logs
docker logs --tail=100 pop-render-worker-1

# 3. Check job in Redis
redis-cli -h $REDIS_HOST GET rq:job:{job_id}

# 4. Check database
psql -h $DB_HOST -U $DB_USER -d aso_render -c "
SELECT id, status, started_at, NOW() - started_at as duration
FROM renders
WHERE status='started'
ORDER BY started_at;
"

# 5. Check system resources
docker stats pop-render-worker-1

# 6. Attach to worker process (if needed)
docker exec -it pop-render-worker-1 /bin/bash
# Inside container:
ps aux
top
strace -p {worker_pid}  # Trace system calls
```

**Resolution:**
```bash
# 1. If worker is deadlocked, restart
docker restart pop-render-worker-1

# 2. If job is truly stuck, mark as failed
psql -h $DB_HOST -U $DB_USER -d aso_render -c "
UPDATE renders
SET status='failed', error_message='Job timeout - stuck for >1 hour', completed_at=NOW()
WHERE id='{render_id}' AND status='started' AND started_at < NOW() - INTERVAL '1 hour';
"

# 3. Remove from Redis queue
redis-cli -h $REDIS_HOST DEL rq:job:{job_id}
```

### Investigating Rendering Errors

**Procedure:**

**1. Identify error pattern:**
```sql
-- Group errors by message
SELECT error_message, COUNT(*) as count
FROM renders
WHERE status='failed' AND created_at > NOW() - INTERVAL '24 hours'
GROUP BY error_message
ORDER BY count DESC;
```

**2. Reproduce error locally:**
```bash
# Download problematic asset
mc cp myminio/render-assets/uploads/{asset_id}/{filename} /tmp/test_image.jpg

# Run pipeline locally
cd platform/pop-render
python3 <<EOF
from PIL import Image
from service.pipelines import get_pipeline

image = Image.open('/tmp/test_image.jpg')
pipeline = get_pipeline('pop-poster', {})
try:
    output = pipeline.render(image)
    print("Success")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
EOF
```

**3. Fix and redeploy:**
```bash
# Fix code in service/pipelines/pop_poster.py
# Test fix locally
# Build new image
docker build -t aso/pop-render:1.0.1 .
docker push registry.example.com/aso/pop-render:1.0.1

# Deploy
kubectl set image deployment/pop-render-worker worker=registry.example.com/aso/pop-render:1.0.1 -n pop-render
```

**4. Requeue failed jobs:**
```python
# Run requeue script for specific error
python3 requeue_failed.py --error-pattern "KeyError: 'k'"
```

### Performance Tuning

#### Worker Count Optimization

**Formula:**
```
Optimal Workers = (CPU Cores × 0.75) to (CPU Cores × 1.0)
```

**Example:**
- 8-core machine: 6-8 workers
- 16-core machine: 12-16 workers

**Monitor:**
```promql
# CPU utilization
rate(process_cpu_seconds_total[5m]) * 100

# Queue depth vs workers
render_queue_depth / count(up{job="pop-render-worker"})
```

**Adjust:**
```bash
# If CPU < 60% and queue growing: add workers
kubectl scale deployment/pop-render-worker --replicas=12 -n pop-render

# If CPU > 90% consistently: reduce workers
kubectl scale deployment/pop-render-worker --replicas=6 -n pop-render
```

#### Redis Memory Tuning

**Check memory usage:**
```bash
redis-cli -h $REDIS_HOST INFO memory
```

**Key metrics:**
- `used_memory_human`: Current memory usage
- `maxmemory_human`: Memory limit
- `mem_fragmentation_ratio`: Should be 1.0-1.5

**Optimization:**
```bash
# Set memory limit
redis-cli -h $REDIS_HOST CONFIG SET maxmemory 2gb
redis-cli -h $REDIS_HOST CONFIG SET maxmemory-policy allkeys-lru

# If fragmentation > 1.5, restart Redis
sudo systemctl restart redis
```

**Job result TTL tuning:**
```python
# Reduce result TTL to save memory
# In service/queue.py
job = queue.enqueue(
    process_render,
    ...,
    result_ttl=3600,    # 1 hour instead of 24 hours
    failure_ttl=86400,  # 1 day instead of 7 days
)
```

## Risk Mitigation Procedures

### Risk 1: Database Connection Pool Exhaustion

**Mitigation:**
- Monitor `db_connections_active` metric
- Set alert at 80% of max connections
- Increase pool size if needed
- Implement connection timeout

**Procedure:**
```bash
# Check active connections
psql -h $DB_HOST -U $DB_USER -d aso_render -c "SELECT count(*) FROM pg_stat_activity WHERE datname='aso_render';"

# If approaching limit, increase pool size
# Edit service/database.py: max_connections=20

# Terminate idle connections
psql -h $DB_HOST -U postgres -d aso_render -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname='aso_render' AND state='idle' AND state_change < NOW() - INTERVAL '10 minutes';
"
```

### Risk 2: Redis Queue Data Loss

**Mitigation:**
- Enable AOF persistence
- Regular backups
- Monitor AOF size
- Implement queue depth alerts

**Procedure:**
```bash
# Enable AOF (if not already)
redis-cli -h $REDIS_HOST CONFIG SET appendonly yes
redis-cli -h $REDIS_HOST CONFIG REWRITE

# Backup AOF
cp /var/lib/redis/appendonly.aof /backup/redis/appendonly_$(date +%Y%m%d).aof

# Monitor AOF size
du -sh /var/lib/redis/appendonly.aof

# If AOF lost, requeue from database
python3 requeue_failed.py --all-pending
```

### Risk 3: MinIO Storage Capacity

**Mitigation:**
- Monitor `render_storage_bytes_total` metric
- Set alert at 80% capacity
- Implement lifecycle policies
- Regular cleanup

**Procedure:**
```bash
# Check storage usage
mc du myminio/render-assets

# If approaching limit:
# 1. Clean up old renders
python3 cleanup_old_renders.py --days 60

# 2. Archive to cold storage
mc mirror myminio/render-assets s3://archive-bucket/render-assets

# 3. Expand storage
# Add new MinIO nodes or increase volume size
```

### Risk 4: Worker Memory Leaks

**Mitigation:**
- Monitor `process_resident_memory_bytes` metric
- Set alert if memory grows >1.5GB
- Implement periodic worker restarts
- Profile memory usage

**Procedure:**
```bash
# Check memory usage
docker stats --no-stream | grep pop-render-worker

# If memory leak detected:
# 1. Restart affected workers
docker restart pop-render-worker-1

# 2. Implement automatic restart policy
# Add to cron:
0 */4 * * * docker restart pop-render-worker-1  # Restart every 4 hours

# 3. Investigate leak
docker exec pop-render-worker-1 python3 -m memory_profiler service/pipelines/__init__.py
```

### Risk 5: Algorithm Non-Determinism

**Mitigation:**
- Pin library versions in requirements.txt
- Use fixed random seeds
- Implement regression testing
- Version algorithms

**Procedure:**
```bash
# Verify determinism
python3 test_determinism.py

# If non-deterministic output detected:
# 1. Check library versions
pip list | grep -E "(scikit-learn|numpy|opencv)"

# 2. Pin versions
echo "scikit-learn==1.4.0" >> requirements.txt
echo "numpy==1.26.3" >> requirements.txt

# 3. Rebuild and redeploy
docker build -t aso/pop-render:1.0.2 .
```

### Risk 6: High Latency from MinIO

**Mitigation:**
- Monitor `storage_operation_duration_seconds` metric
- Set alert at P95 > 10 seconds
- Implement retry logic
- Use MinIO distributed mode

**Procedure:**
```bash
# Check MinIO performance
mc admin trace myminio

# If latency issues:
# 1. Check network
ping -c 10 ${MINIO_ENDPOINT}

# 2. Check MinIO load
mc admin info myminio

# 3. Scale MinIO horizontally
# Add MinIO nodes to distributed cluster

# 4. Increase timeouts
# Edit service/storage.py: read_timeout=120
```

### Risk 7: Queue Backlog During Peak Load

**Mitigation:**
- Monitor `render_queue_depth` metric
- Set alert at >100 jobs
- Implement auto-scaling
- Add workers proactively

**Procedure:**
```bash
# Check queue depth
redis-cli -h $REDIS_HOST LLEN rq:queue:renders

# If backlog >100:
# 1. Scale workers immediately
kubectl scale deployment/pop-render-worker --replicas=16 -n pop-render

# 2. Check worker health
kubectl get pods -n pop-render -l app=pop-render-worker

# 3. Monitor progress
watch -n 5 'redis-cli -h $REDIS_HOST LLEN rq:queue:renders'

# 4. Once backlog cleared, scale down
kubectl scale deployment/pop-render-worker --replicas=8 -n pop-render
```

## Summary Checklist

### Daily Operations
- [ ] Check health endpoint: `curl http://pop-render-api:8089/health`
- [ ] Verify queue depth: `redis-cli LLEN rq:queue:renders`
- [ ] Check failed jobs: `SELECT COUNT(*) FROM renders WHERE status='failed'`
- [ ] Monitor Grafana dashboard
- [ ] Review error logs

### Weekly Operations
- [ ] Review alert history
- [ ] Check storage capacity
- [ ] Analyze performance trends
- [ ] Review failed job patterns
- [ ] Update documentation

### Monthly Operations
- [ ] Database backup verification
- [ ] Storage cleanup (old renders)
- [ ] Performance optimization review
- [ ] Capacity planning
- [ ] Security patch updates

### Incident Response
1. Identify impact (users affected, severity)
2. Check health endpoint and metrics
3. Review recent changes (deployments, config)
4. Check logs (API, workers, dependencies)
5. Implement mitigation (restart, scale, rollback)
6. Monitor recovery
7. Document incident and root cause
8. Implement preventive measures
