#!/usr/bin/env bash

# k8s-cost-operator quick reference

echo "📚 K8s Cost Optimization Operator - Quick Reference"
echo "====================================================="
echo ""

echo "🔧 Installation & Tests"
echo "  • Test unitaires:        python test.py"
echo "  • Exemple local:         python example.py"
echo "  • Build Docker:          docker build -t cost-operator:latest ."
echo "  • Déploiement auto:      bash deploy.sh"
echo ""

echo "📋 Commandes Kubernetes"
echo "  • Installer CRD+RBAC:    kubectl apply -f k8s/crd.yaml"
echo "  • Installer opérateur:   kubectl apply -f k8s/deployment.yaml"
echo "  • Créer rapport:         kubectl apply -f k8s/example-costreport.yaml"
echo ""

echo "🔍 Monitoring"
echo "  • Logs opérateur:        kubectl -n kube-system logs -f deployment/cost-operator"
echo "  • Status CostReport:     kubectl describe costreport -A"
echo "  • ConfigMaps rapports:   kubectl get configmaps -l type=cost-report -A"
echo ""

echo "📊 Rapport"
echo "  • Lister rapports:       kubectl get configmaps -l type=cost-report"
echo "  • Extraire rapport:      kubectl get configmap REPORT_NAME -o jsonpath='{.data.report\\.html}' > report.html"
echo "  • Afficher HTML:         open report.html (Mac) ou start report.html (Windows)"
echo ""

echo "🧠 Structure du code"
echo "  ├── main.py              Opérateur kopf + boucle principale"
echo "  ├── metrics.py           Collecte Prometheus/metrics-server"
echo "  ├── analyzer.py          Analyse surprovisionnement/idle"
echo "  ├── report.py            Génération HTML Jinja2"
echo "  └── k8s/                 Manifests Kubernetes (CRD, RBAC, Deployment)"
echo ""

echo "📖 Documentation complète: README.md"
echo ""
