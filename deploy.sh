#!/bin/bash

# Script de déploiement du Cost Optimization Operator

set -e

echo "🚀 Déploiement du K8s Cost Optimization Operator"
echo "=================================================="

# Vérifications préalables
echo "✅ Vérification des prérequis..."

if ! command -v kubectl &> /dev/null; then
    echo "❌ kubectl n'est pas installé"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "❌ docker n'est pas installé"
    exit 1
fi
if ! command -v helm &> /dev/null; then
    echo "❌ helm n'est pas installé"
    exit 1
fi

read -p "📦 Image repository complète (ex: harbor.dev01.sayzx.fr/admin/cost-operator): " IMAGE_REPOSITORY
read -p "🏷️  Tag de l'image (ex: latest): " IMAGE_TAG
IMAGE_TAG=${IMAGE_TAG:-latest}
read -p "📁 Namespace Helm (ex: cost-operator-system): " NAMESPACE
NAMESPACE=${NAMESPACE:-cost-operator-system}
read -p "🏷️  Nom du release Helm (ex: cost-operator): " RELEASE_NAME
RELEASE_NAME=${RELEASE_NAME:-cost-operator}

FULL_IMAGE="${IMAGE_REPOSITORY}:${IMAGE_TAG}"

echo ""
echo "🏗️  Construction de l'image Docker..."
docker build -t "${FULL_IMAGE}" .

echo ""
echo "📤 Push de l'image vers le registry..."
docker push "${FULL_IMAGE}"

echo ""
echo "📝 Déploiement Helm..."
kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
helm upgrade --install "${RELEASE_NAME}" ./helm/cost-operator \
    --namespace "${NAMESPACE}" \
    --create-namespace \
    --wait \
    --timeout 5m \
    --set image.repository="${IMAGE_REPOSITORY}" \
    --set image.tag="${IMAGE_TAG}"

echo ""
echo "✅ Déploiement terminé"
kubectl -n "${NAMESPACE}" get pods -l app.kubernetes.io/instance="${RELEASE_NAME}"
echo ""
echo "Logs: kubectl -n ${NAMESPACE} logs -f deployment/${RELEASE_NAME}-cost-operator"
