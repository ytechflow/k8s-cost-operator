# Helm Chart: Cost Operator

## 📋 Description

Chart Helm pour déployer le **K8s Cost Optimization Operator** sur Kubernetes.

## 🚀 Installation rapide

### 1. Ajouter le repository (quand publié)

```bash
helm repo add cost-operator https://github.com/sayzx/k8s-cost-operator/helm
helm repo update
```

### 2. Installation en local

```bash
# Installation simple
helm install cost-operator ./helm/cost-operator \
  --namespace cost-operator-system \
  --create-namespace

# Ou avec tes valeurs
helm install cost-operator ./helm/cost-operator \
  --namespace cost-operator-system \
  --values ./helm/cost-operator/examples/values-production.yaml
```

## ⚙️ Configuration

Tous les paramètres se font via `values.yaml`:

### Image Docker

```yaml
image:
  registry: docker.io
  repository: yourusername/cost-operator
  tag: "1.0.0"
  pullPolicy: IfNotPresent
```

### Prometheus (optionnel)

```yaml
config:
  prometheusUrl: "http://prometheus:9090"
  prometheusTimeout: "10s"
```

Si pas de Prometheus → utilise metrics-server automatiquement.

### Ressources

```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

### Rapports automatiques

```yaml
reports:
  enabled: true
  default:
    name: "daily-analysis"
    namespace: default
    scope: "cluster"
    schedule: "0 0 * * *"  # Cron format
    output: "configmap"     # ou "file"
    autoApply: false
```

### Persistence (optionnel)

```yaml
persistence:
  enabled: true
  storageClassName: "standard"
  size: "5Gi"
  mountPath: "/reports"
```

## 📦 Exemples

### Basique (Docker Hub)

```bash
helm install cost-operator ./helm/cost-operator \
  --values ./helm/cost-operator/examples/values-basic.yaml
```

### Production (avec Prometheus)

```bash
helm install cost-operator ./helm/cost-operator \
  --values ./helm/cost-operator/examples/values-production.yaml
```

### Avec Persistence

```bash
helm install cost-operator ./helm/cost-operator \
  --values ./helm/cost-operator/examples/values-with-persistence.yaml
```

## 🔄 Mise à jour

```bash
# Mettre à jour les valeurs
helm upgrade cost-operator ./helm/cost-operator \
  --values ./helm/cost-operator/examples/values-production.yaml

# Ou modifier un paramètre uniquement
helm upgrade cost-operator ./helm/cost-operator \
  --set image.tag="1.1.0"
```

## 🗑️ Désinstallation

```bash
# Désinstalle tout (garde les CRD)
helm uninstall cost-operator --namespace cost-operator-system

# Ou avec suppression complète
helm uninstall cost-operator --namespace cost-operator-system
kubectl delete crd costreports.cost.k8s.io
```

## 📋 Vérification

```bash
# Vérifier l'installation
helm status cost-operator --namespace cost-operator-system

# Voir les valeurs appliquées
helm get values cost-operator --namespace cost-operator-system

# Voir les manifests générés
helm template cost-operator ./helm/cost-operator \
  --values ./helm/cost-operator/examples/values-production.yaml
```

## 🔍 Troubleshooting

```bash
# Pods logs
kubectl -n cost-operator-system logs -f deployment/cost-operator

# Voir les CostReports créés
kubectl get costreports -A

# Voir les rapports générés
kubectl get configmaps -l type=cost-report -A
```

## 🔐 Sécurité

Le chart crée automatiquement:
- ✅ ServiceAccount
- ✅ ClusterRole + ClusterRoleBinding (RBAC minimal)
- ✅ Pod security context (non-root, read-only, etc.)

## 📊 Valeurs disponibles

Voir [values.yaml](values.yaml) pour la liste complète de tous les paramètres configurables.
