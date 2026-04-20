#!/bin/bash

# Script de déploiement Helm - Cost Operator

set -e

echo ""
echo "🚀 Cost Operator - Helm Deployment"
echo "===================================="
echo ""

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Demander les paramètres
read -p "📦 Nom du release Helm (ex: cost-operator): " RELEASE_NAME
RELEASE_NAME=${RELEASE_NAME:-cost-operator}

read -p "📁 Namespace (ex: kube-system): " NAMESPACE
NAMESPACE=${NAMESPACE:-kube-system}

read -p "🏷️  Tag de l'image (ex: 1.0.0): " IMAGE_TAG
IMAGE_TAG=${IMAGE_TAG:-1.0.0}

read -p "🔗 Registry Docker (ex: docker.io/yourusername): " REGISTRY
REGISTRY=${REGISTRY:-docker.io/yourusername}

read -p "🔥 Mode production? (y/n): " IS_PRODUCTION
IS_PRODUCTION=${IS_PRODUCTION:-n}

echo ""
echo "📝 Résumé de la configuration:"
echo "   Release: $RELEASE_NAME"
echo "   Namespace: $NAMESPACE"
echo "   Image: $REGISTRY/cost-operator:$IMAGE_TAG"
echo "   Production: $IS_PRODUCTION"
echo ""

read -p "❓ Continuer? (y/n): " CONFIRM
if [[ $CONFIRM != "y" ]]; then
    echo "Annulé."
    exit 0
fi

# Créer le namespace si nécessaire
echo ""
echo "✅ Étape 1: Préparation..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo "   Namespace $NAMESPACE prêt"

# Générer les valeurs
echo ""
echo "✅ Étape 2: Génération des valeurs..."
cat > /tmp/helm-values.yaml <<EOF
image:
  registry: $(echo $REGISTRY | sed 's|/.*||')
  repository: $(echo $REGISTRY | sed 's|^[^/]*||;s|^/||')/cost-operator
  tag: "$IMAGE_TAG"

namespace: $NAMESPACE

config:
  clusterName: "kubernetes"
  logLevel: "INFO"

reports:
  enabled: true
  default:
    name: "daily-analysis"
    namespace: default
    schedule: "0 0 * * *"
EOF

if [[ $IS_PRODUCTION == "y" ]]; then
    cat >> /tmp/helm-values.yaml <<EOF

resources:
  requests:
    cpu: 200m
    memory: 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi

replicaCount: 1

config:
  logLevel: "INFO"
EOF
fi

echo "   ✅ Fichier de valeurs généré"

# Valider la chart
echo ""
echo "✅ Étape 3: Validation..."
helm lint ./helm/cost-operator
echo "   ✅ Chart validée"

# Dry-run
echo ""
echo "✅ Étape 4: Dry-run..."
helm install $RELEASE_NAME ./helm/cost-operator \
  --namespace $NAMESPACE \
  --values /tmp/helm-values.yaml \
  --dry-run --debug > /tmp/helm-dry-run.yaml
echo "   ✅ Dry-run réussi"

# Installation
echo ""
echo "✅ Étape 5: Installation Helm..."
helm install $RELEASE_NAME ./helm/cost-operator \
  --namespace $NAMESPACE \
  --values /tmp/helm-values.yaml

echo ""
echo "✅ Étape 6: Attente du déploiement..."
kubectl rollout status deployment/$RELEASE_NAME -n $NAMESPACE --timeout=2m

echo ""
echo "✅ Déploiement réussi!"
echo ""
echo "📋 Prochaines étapes:"
echo "   • Voir le statut:       helm status $RELEASE_NAME -n $NAMESPACE"
echo "   • Voir les logs:        kubectl logs -f -l app.kubernetes.io/instance=$RELEASE_NAME -n $NAMESPACE"
echo "   • Voir les rapports:    kubectl get configmaps -l type=cost-report -A"
echo ""

# Montrer la structure
echo "📊 Ressources créées:"
kubectl get all -n $NAMESPACE -l app.kubernetes.io/instance=$RELEASE_NAME
echo ""
kubectl get crd costreports.cost.k8s.io
echo ""

# Nettoyer
rm -f /tmp/helm-values.yaml /tmp/helm-dry-run.yaml

echo "✨ C'est bon! L'opérateur tourne maintenant sur ton cluster."
echo ""
