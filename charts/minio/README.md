# MinIO for STOA Platform

Object storage for Error Snapshots (CAB-397).

## Quick Start

### 1. Add MinIO Helm repo

```bash
helm repo add minio https://charts.min.io/
helm repo update
```

### 2. Create secrets

```bash
# Edit secret.yaml with production credentials first!
kubectl apply -f secret.yaml
```

### 3. Install MinIO

```bash
helm install minio minio/minio \
  -n stoa-system \
  -f values.yaml \
  --set existingSecret=minio-credentials
```

### 4. Run setup job

```bash
kubectl apply -f setup-job.yaml
```

### 5. Verify installation

```bash
# Check MinIO pod
kubectl get pods -n stoa-system -l app=minio

# Check bucket was created
kubectl logs -n stoa-system job/minio-setup-error-snapshots

# Port-forward to access console
kubectl port-forward svc/minio-console 9001:9001 -n stoa-system
# Open http://localhost:9001
```

## Configuration

### Environment Variables for Control-Plane-API

```bash
STOA_SNAPSHOTS_ENABLED=true
STOA_SNAPSHOTS_STORAGE_TYPE=minio
STOA_SNAPSHOTS_STORAGE_ENDPOINT=minio.stoa-system:9000
STOA_SNAPSHOTS_STORAGE_BUCKET=error-snapshots
STOA_SNAPSHOTS_STORAGE_ACCESS_KEY=error-snapshots-user
STOA_SNAPSHOTS_STORAGE_SECRET_KEY=error-snapshots-secret-key-change-me
STOA_SNAPSHOTS_STORAGE_USE_SSL=false
STOA_SNAPSHOTS_RETENTION_DAYS=30
```

### Lifecycle Policy

The setup job configures a 30-day expiration policy:

```json
{
  "Rules": [
    {
      "ID": "expire-after-30-days",
      "Status": "Enabled",
      "Filter": { "Prefix": "" },
      "Expiration": { "Days": 30 }
    }
  ]
}
```

## Production Recommendations

1. **Change default credentials** in `secret.yaml`
2. **Use distributed mode** for high availability:
   ```yaml
   mode: distributed
   replicas: 4
   ```
3. **Enable ingress** with TLS for console access
4. **Increase storage** size based on expected snapshot volume
5. **Enable metrics** for Prometheus monitoring

## Storage Estimation

Average snapshot size: ~5-10 KB (gzipped JSON)

| Errors/day | 30-day storage |
|------------|----------------|
| 100        | ~15-30 MB      |
| 1,000      | ~150-300 MB    |
| 10,000     | ~1.5-3 GB      |

## Troubleshooting

### Check MinIO logs

```bash
kubectl logs -n stoa-system -l app=minio
```

### Manual bucket operations

```bash
# Port-forward MinIO API
kubectl port-forward svc/minio 9000:9000 -n stoa-system

# Use mc client
mc alias set local http://localhost:9000 minioadmin minioadmin123
mc ls local/error-snapshots
mc ilm ls local/error-snapshots
```
