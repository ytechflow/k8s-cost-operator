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

# Demander le registry
read -p "📦 Registry Docker (ex: docker.io/username): " REGISTRY
read -p "🏷️  Tag de l'image (ex: latest): " TAG
TAG=${TAG:-latest}

# Build et push de l'image
echo ""
echo "🏗️  Construction de l'image Docker..."
docker build -t ${REGISTRY}/cost-operator:${TAG} .

echo ""
echo "📤 Push de l'image vers le registry..."
docker push ${REGISTRY}/cost-operator:${TAG}

# Mettre à jour le deployment avec la bonne image
echo ""
echo "⚙️  Mise à jour du deployment..."
sed "s|cost-operator:latest|${REGISTRY}/cost-operator:${TAG}|g" k8s/deployment.yaml > k8s/deployment-final.yaml

# Créer le namespace si nécessaire
echo ""
echo "📝 Installation des ressources Kubernetes..."
kubectl apply -f k8s/crd.yaml

# Attendre la création de la CRD
echo "⏳ Attente de la création de la CRD..."
sleep 3

# Installer le deployment
kubectl apply -f k8s/deployment-final.yaml

echo ""
echo "✅ Déploiement terminé!"
echo ""
echo "Vérification du statut..."
kubectl -n kube-system get deployment cost-operator
kubectl -n kube-system get pods -l app=cost-operator

echo ""
echo "📊 Créer un rapport avec:"
echo "   kubectl apply -f k8s/example-costreport.yaml"
echo ""
echo "📋 Voir les logs avec:"
echo "   kubectl -n kube-system logs -f deployment/cost-operator"
