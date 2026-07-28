# Preuve d'exécution — Gitea déployé et persistant

```bash
# Assertion : Gitea répond et son API est servie
kubectl -n ci exec deploy/probe -- curl -sf http://gitea.ci.svc.cluster.local:3000/api/v1/version
```
