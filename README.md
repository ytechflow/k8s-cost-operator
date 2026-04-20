# K8s Cost Optimization Operator

Un opérateur Kubernetes complet pour analyser l'utilisation des ressources (CPU/mémoire) et générer des recommandations d'optimisation des coûts.

## 🎯 Objectifs

- **Collecte des métriques**: CPU, mémoire, requests/limits depuis Prometheus ou metrics-server
- **Analyse intelligente**: Détecte le surprovisionnement, sous-provisionnement, pods idle
- **Rapports HTML**: Génère des rapports visuels avec recommandations
- **Automatisation**: Exécution périodique selon schedule cron
- **Estimation de coûts**: Calcule les économies potentielles
- **Stockage flexible**: ConfigMap ou fichier local
- **Multi-namespace**: Support de l'analyse par namespace ou cluster

## 📋 Structure du Projet

```
k8s-cost-operator/
├── main.py              # Opérateur kopf (point d'entrée)
├── metrics.py           # Collecte des métriques
├── analyzer.py          # Analyse des optimisations
├── report.py            # Génération des rapports HTML
├── requirements.txt     # Dépendances Python
├── Dockerfile           # Image Docker
├── README.md
├── k8s/
│   ├── crd.yaml         # Définition de la CRD CostReport + RBAC
│   ├── deployment.yaml  # Deployment de l'opérateur
│   └── example-costreport.yaml  # Exemples d'utilisation
└── templates/           # Templates Jinja2 (future)
```

## ⚙️ Prérequis

- Kubernetes 1.20+
- Python 3.9+
- Prometheus (optionnel, metrics-server par défaut)

## 🚀 Installation

### 1. Construire l'image Docker

```bash
docker build -t cost-operator:latest .
```

### 2. Pousser vers votre registry

```bash
docker tag cost-operator:latest your-registry/cost-operator:latest
docker push your-registry/cost-operator:latest
```

### 3. Installer la CRD et le RBAC

```bash
kubectl apply -f k8s/crd.yaml
```

### 4. Installer le Deployment

Modifiez `k8s/deployment.yaml` pour utiliser votre image registry:

```bash
kubectl apply -f k8s/deployment.yaml
```

### 5. Vérifier l'installation

```bash
kubectl -n kube-system logs -f deployment/cost-operator
kubectl -n kube-system get pods -l app=cost-operator
```

## 📖 Utilisation

### Créer un rapport automatique

```bash
kubectl apply -f k8s/example-costreport.yaml
```

### Consulter le rapport généré

Le rapport est stocké dans un ConfigMap:

```bash
# Lister les reports
kubectl get configmaps -l type=cost-report

# Consulter le rapport
kubectl get configmap cost-report-daily-analysis-YYYYMMDD-HHMMSS -o jsonpath='{.data.report\.html}' > report.html

# Ouvrir dans le navigateur
open report.html
```

### Configuration avancée

#### Avec Prometheus

```yaml
apiVersion: cost.k8s.io/v1
kind: CostReport
metadata:
  name: prometheus-report
  namespace: default
spec:
  scope: cluster
  schedule: "0 */6 * * *"  # Toutes les 6 heures
  output: configmap
  prometheusUrl: "http://prometheus.monitoring:9090"
  autoApply: false
```

#### Avec fichiers locaux (et PersistentVolume)

```yaml
apiVersion: cost.k8s.io/v1
kind: CostReport
metadata:
  name: file-report
  namespace: production
spec:
  scope: namespace
  schedule: "0 2 * * *"  # Chaque jour à 2h du matin
  output: file
  outputPath: "/reports"
  autoApply: false
```

## 🔍 Qu'analyse l'opérateur?

### 1. **Surprovisionnement CPU/Mémoire**

Détecte quand les requests/limits sont bien supérieurs à l'utilisation réelle:
- Seuil par défaut: < 30% d'utilisation
- Recommande une réduction avec 20% de marge de sécurité

### 2. **Pods Idle**

Identifie les pods avec très faible consommation:
- CPU < 10m (0.01 cores)
- Mémoire < 50 MiB
- Recommande la suppression

### 3. **Sous-provisionnement (Throttling)**

Détecte quand les pods atteignent leurs limites régulièrement

### 4. **Replicas inutiles**

Analyse les déploiements avec replicas non-ready

## 💰 Modèle de coûts

Par défaut (peut être personnalisé):
- **CPU**: $10/core/mois
- **Mémoire**: $1/GiB/mois

Les économies sont estimées basées sur:
```
Économies = (CPU_reduction * 10 + Memory_reduction_GiB * 1) * nombre_replicas
```

## 🎓 Développement

### Environnement local

```bash
# Créer un venv
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt

# Exécuter localement (avec kubeconfig)
python main.py
```

### Tester l'analyse

```python
from metrics import MetricsCollector
from analyzer import CostAnalyzer
from report import ReportGenerator

# Collecte
collector = MetricsCollector(prometheus_url="http://localhost:9090")

# Analyse
analyzer = CostAnalyzer(collector)
recommendations = analyzer.analyze()

# Rapport
generator = ReportGenerator(analyzer)
html = generator.generate_html()

# Sauvegarde
with open("test_report.html", "w") as f:
    f.write(html)
```

## 📊 Format du Rapport

Le rapport HTML inclut:

✅ **Header**: Date, cluster, nombre de namespaces/pods
✅ **Summary**: Économies potentielles, score d'optimisation, stats
✅ **Recommandations**: Groupées par priorité (haute/medium/basse)
✅ **Tableau récapitulatif**: Vue synthétique
✅ **Résumé par namespace**: Statistiques par namespace
✅ **Design responsive**: CSS intégré, imprimable

## ⚠️ Mode Auto-Apply (prudence!)

Quand `autoApply: true`:

```yaml
apiVersion: cost.k8s.io/v1
kind: CostReport
metadata:
  name: auto-apply-report
spec:
  autoApply: true  # ⚠️ Attention!
  # ... autres paramètres
```

**L'opérateur appliquera automatiquement:**
- Scale down des déploiements

**NE s'applique PAS automatiquement** (nécessite validation):
- Modification des CPU/mémoire requests/limits (recréation des pods)

## 🔐 Sécurité

- Utilisateur non-root (UID 1000)
- Read-only filesystem
- RBAC limité aux ressources nécessaires
- Pas d'accès au secret de l'API

## 🐛 Troubleshooting

### L'opérateur n'est pas actif

```bash
# Vérifier les logs
kubectl -n kube-system logs deployment/cost-operator

# Vérifier les RBAC
kubectl auth can-i list costreports --as=system:serviceaccount:kube-system:cost-operator

# Vérifier la CRD
kubectl get crd | grep costreports
```

### Les métriques ne sont pas collectées

```bash
# Vérifier Prometheus
kubectl port-forward -n monitoring svc/prometheus 9090:9090
# Visiter http://localhost:9090

# Vérifier metrics-server
kubectl get deployment metrics-server -n kube-system
```

### Le rapport est vide

Vérifier qu'il y a des pods avec requests/limits définis:

```bash
kubectl describe pod -A | grep -A 5 "Limits\|Requests"
```

## 📝 Licence

MIT

## 🤝 Contribution

Les contributions sont bienvenues! Merci de tester avant de soumettre une PR.

## 📚 Ressources

- [Kopf Documentation](https://kopf.readthedocs.io/)
- [Kubernetes Python Client](https://github.com/kubernetes-client/python)
- [Prometheus HTTP API](https://prometheus.io/docs/prometheus/latest/querying/api/)
- [K8s Best Practices](https://kubernetes.io/docs/concepts/workloads/pods/resources/)
