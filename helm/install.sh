#!/bin/bash

set -euo pipefail

echo ""
echo "🚀 Cost Operator - Helm Deployment"
echo "===================================="
echo ""

if ! command -v helm >/dev/null 2>&1; then
    echo "❌ helm n'est pas installé"
    exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
    echo "❌ kubectl n'est pas installé"
    exit 1
fi

read -p "📦 Nom du release Helm (ex: cost-operator): " RELEASE_NAME
RELEASE_NAME=${RELEASE_NAME:-cost-operator}

read -p "📁 Namespace (ex: cost-operator-system): " NAMESPACE
NAMESPACE=${NAMESPACE:-cost-operator-system}

read -p "🏷️  Repository complet de l'image (ex: harbor.dev01.sayzx.fr/admin/cost-operator): " IMAGE_REPOSITORY
read -p "🏷️  Tag de l'image (ex: latest): " IMAGE_TAG
IMAGE_TAG=${IMAGE_TAG:-latest}

read -p "🌐 URL Prometheus (optionnel): " PROMETHEUS_URL
read -p "🏷️  Nom du cluster (ex: kubernetes): " CLUSTER_NAME
CLUSTER_NAME=${CLUSTER_NAME:-kubernetes}

PROMETHEUS_ARGS=()
if [[ -n "$PROMETHEUS_URL" ]]; then
    PROMETHEUS_ARGS+=(--set "config.prometheusUrl=$PROMETHEUS_URL")
fi

echo ""
echo "📝 Résumé de la configuration:"
echo "   Release: $RELEASE_NAME"
echo "   Namespace: $NAMESPACE"
echo "   Image: $IMAGE_REPOSITORY:$IMAGE_TAG"
echo "   Cluster: $CLUSTER_NAME"
echo ""

read -p "❓ Continuer? (y/n): " CONFIRM
if [[ $CONFIRM != "y" ]]; then
    echo "Annulé."
    exit 0
fi

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install "$RELEASE_NAME" ./cost-operator \
    --namespace "$NAMESPACE" \
    --create-namespace \
    --wait \
    --timeout 5m \
    --set image.repository="$IMAGE_REPOSITORY" \
    --set image.tag="$IMAGE_TAG" \
    --set config.clusterName="$CLUSTER_NAME" \
    "${PROMETHEUS_ARGS[@]}"

echo ""
echo "✅ Déploiement réussi!"
echo ""
echo "📋 Statut:"
kubectl get all -n "$NAMESPACE" -l app.kubernetes.io/instance="$RELEASE_NAME"
echo ""
echo "📊 CRD:"
kubectl get crd costreports.cost.k8s.io
