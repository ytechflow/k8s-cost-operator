# 📚 Guide Helm - Cost Operator

## 🚀 Installation rapide (3 étapes)

### 1️⃣ Build l'image Docker

```bash
docker build -t yourusername/cost-operator:1.0.0 .
docker push yourusername/cost-operator:1.0.0
```

### 2️⃣ Install avec Helm

```bash
# Installation simple
helm install cost-operator ./helm/cost-operator \
  --namespace kube-system \
  --create-namespace \
  --set image.repository=yourusername/cost-operator \
  --set image.tag=1.0.0

# OU script automatisé
bash helm/install.sh
```

### 3️⃣ Vérifier l'installation

```bash
kubectl get pods -n kube-system -l app.kubernetes.io/name=cost-operator
kubectl logs -f -n kube-system deployment/cost-operator
```

---

## 📋 Commandes Helm courantes

### Installation

```bash
# Basique
helm install cost-operator ./helm/cost-operator -n kube-system

# Avec valeurs personnalisées
helm install cost-operator ./helm/cost-operator \
  --namespace kube-system \
  --values ./helm/cost-operator/examples/values-production.yaml

# Avec override inline
helm install cost-operator ./helm/cost-operator \
  --set image.tag=1.0.0 \
  --set config.prometheusUrl="http://prometheus:9090"

# Sans créer le CostReport (rapports créés manuellement)
helm install cost-operator ./helm/cost-operator \
  --set reports.enabled=false
```

### Mise à jour

```bash
# Mettre à jour après modification de values.yaml
helm upgrade cost-operator ./helm/cost-operator -n kube-system

# Mettre à jour un paramètre
helm upgrade cost-operator ./helm/cost-operator \
  --set image.tag=1.0.1

# Mettre à jour depuis un fichier values
helm upgrade cost-operator ./helm/cost-operator \
  --values ./helm/cost-operator/examples/values-production.yaml
```

### Verification

```bash
# Status du release
helm status cost-operator -n kube-system

# Voir les valeurs appliquées
helm get values cost-operator -n kube-system

# Voir tous les manifests
helm template cost-operator ./helm/cost-operator

# Voir un template spécifique
helm template cost-operator ./helm/cost-operator --show-only templates/deployment.yaml

# Dry-run (simule sans appliquer)
helm install cost-operator ./helm/cost-operator --dry-run --debug
```

### Désinstallation

```bash
# Désinstall (garde les CRD et les ConfigMaps)
helm uninstall cost-operator -n kube-system

# Désinstall + suppression complète
helm uninstall cost-operator -n kube-system
kubectl delete crd costreports.cost.k8s.io
kubectl delete configmaps -l type=cost-report -A
```

### Historique

```bash
# Voir l'historique des releases
helm history cost-operator -n kube-system

# Revenir à une version précédente
helm rollback cost-operator 1 -n kube-system
```

---

## ⚙️ Configuration commune

### Avec Prometheus

```bash
helm install cost-operator ./helm/cost-operator \
  --set config.prometheusUrl="http://prometheus:9090" \
  --set config.prometheusTimeout="15s"
```

### Mode production (multi-replicas, limites élevées)

```bash
helm install cost-operator ./helm/cost-operator \
  --values ./helm/cost-operator/examples/values-production.yaml
```

### Avec persistence (fichiers locaux)

```bash
helm install cost-operator ./helm/cost-operator \
  --values ./helm/cost-operator/examples/values-with-persistence.yaml
```

### Rapports multi-namespace

```bash
helm install cost-operator ./helm/cost-operator \
  --set reports.enabled=false

# Puis créer les rapports manuellement:
kubectl apply -f - <<'EOF'
apiVersion: cost.k8s.io/v1
kind: CostReport
metadata:
  name: prod-analysis
  namespace: production
spec:
  scope: namespace
  schedule: "0 */6 * * *"
  output: configmap
EOF
```

---

## 🔧 Fichiers values disponibles

| Fichier | Usage |
|---------|-------|
| `values.yaml` | Configuration complète par défaut |
| `values-basic.yaml` | Setup simple (Docker Hub) |
| `values-production.yaml` | Configuration production (Prometheus, haute disponibilité) |
| `values-with-persistence.yaml` | Avec PersistentVolume pour rapports |
| `values-multi-namespace.yaml` | Analyse multi-namespace |

---

## 🔍 Troubleshooting

```bash
# Pods en erreur?
kubectl describe pod -n kube-system -l app.kubernetes.io/name=cost-operator

# Logs complets
kubectl logs -n kube-system deployment/cost-operator --all-containers

# RBAC issues?
kubectl auth can-i list costreports --as=system:serviceaccount:kube-system:cost-operator

# ServiceAccount existe?
kubectl get sa -n kube-system cost-operator

# ConfigMaps de rapports?
kubectl get configmaps -l type=cost-report -A

# Voir le release Helm
helm get all cost-operator -n kube-system
```

---

## 📦 Packager la chart

```bash
# Créer un package .tgz
helm package ./helm/cost-operator
# Produit: cost-operator-1.0.0.tgz

# Publier sur un repository (une fois configuré)
helm repo index .
# Et push sur ton repository
```

---

## 🎯 Cas d'usage courants

### ✅ Déploiement rapide local

```bash
helm install cost-operator ./helm/cost-operator \
  -n kube-system \
  --set image.repository=cost-operator \
  --set image.tag=latest
```

### ✅ Production avec Prometheus

```bash
helm install cost-operator ./helm/cost-operator \
  -n kube-system \
  --values ./helm/cost-operator/examples/values-production.yaml \
  --set image.repository=registry.company.com/cost-operator
```

### ✅ Multi-cluster (avec Helm hooks)

```bash
# Cluster 1
helm install cost-op ./helm/cost-operator \
  --set config.clusterName="prod-us-east-1"

# Cluster 2
helm install cost-op ./helm/cost-operator \
  --set config.clusterName="prod-eu-west-1"
```

---

## 📖 En savoir plus

- [Documentation Helm](https://helm.sh/docs/)
- [Best practices Helm](https://helm.sh/docs/chart_best_practices/)
- [Values.yaml complet](./helm/cost-operator/values.yaml)
