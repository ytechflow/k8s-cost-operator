#!/bin/bash
set -e

# ============================================
# K8s Cost Operator - GitOps Deployment Script
# ============================================

set -e

# Configuration
REGISTRY="ghcr.io"
IMAGE_NAME="ytechflow/cost-operator"
VERSION="${VERSION:-1.0.0}"
NAMESPACE="${NAMESPACE:-cost-operator}"
RELEASE_NAME="cost-operator"
HELM_CHART="./helm/cost-operator"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Vérifications前置检查
check_prerequisites() {
    log_info "Vérification des prérequis..."

    local missing=()

    command -v docker >/dev/null 2>&1 || missing+=("docker")
    command -v helm >/dev/null 2>&1 || missing+=("helm")
    command -v kubectl >/dev/null 2>&1 || missing+=("kubectl")

    if [ ${#missing[@]} -ne 0 ]; then
        log_error "Outils manquants: ${missing[*]}"
        exit 1
    fi

    # Vérifier la connexion au cluster
    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Pas de connexion au cluster Kubernetes"
        exit 1
    fi

    log_success "Prérequis vérifiés"
}

# Construction de l'image Docker
build_image() {
    log_info "Construction de l'image Docker..."

    local full_image="${REGISTRY}/${IMAGE_NAME}:${VERSION}"

    docker build -t "${full_image}" .

    log_success "Image construite: ${full_image}"
    echo "${full_image}"
}

# Push de l'image vers le registry
push_image() {
    local full_image="$1"

    log_info "Push de l'image vers le registry..."

    # Login si nécessaire
    echo "${GHCR_TOKEN}" | docker login "${REGISTRY}" -u "${GHCR_USER}" --password-stdin 2>/dev/null || true

    docker push "${full_image}"

    log_success "Image poussée: ${full_image}"
}

# Mise à jour du tag dans values.yaml
update_values() {
    local full_image="$1"

    log_info "Mise à jour de values.yaml..."

    sed -i "s|image:.*|image:|" "${HELM_CHART}/values.yaml"
    sed -i "s|  registry:.*|  registry: ${REGISTRY}|" "${HELM_CHART}/values.yaml"
    sed -i "s|  repository:.*|  repository: ${IMAGE_NAME}|" "${HELM_CHART}/values.yaml"
    sed -i "s|  tag:.*|  tag: \"${VERSION}\"|" "${HELM_CHART}/values.yaml"

    log_success "values.yaml mis à jour"
}

# Déploiement Helm
deploy_helm() {
    log_info "Déploiement Helm dans le namespace ${NAMESPACE}..."

    # Créer le namespace si nécessaire
    kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    # Upgrade ou install
    helm upgrade --install "${RELEASE_NAME}" "${HELM_CHART}" \
        --namespace "${NAMESPACE}" \
        --create-namespace \
        --wait \
        --timeout 5m \
        -f "${HELM_CHART}/values.yaml" \
        --set image.tag="${VERSION}"

    log_success "Opérateur déployé"
}

# Vérification du déploiement
verify_deployment() {
    log_info "Vérification du déploiement..."

    echo ""
    echo "=== Pods ==="
    kubectl get pods -n "${NAMESPACE}" -l app=cost-operator

    echo ""
    echo "=== Services ==="
    kubectl get svc -n "${NAMESPACE}"

    echo ""
    echo "=== ConfigMap ==="
    kubectl get configmap -n "${NAMESPACE}"

    echo ""
    echo "=== CRD ==="
    kubectl get crd costreports.cost.k8s.io 2>/dev/null || echo "CRD non trouvée"

    # Attendre que le pod soit prêt
    log_info "Attente du démarrage de l'opérateur..."
    kubectl wait --for=condition=ready pod -l app=cost-operator -n "${NAMESPACE}" --timeout=120s 2>/dev/null && \
        log_success "Opérateur prêt!" || \
        log_warn "L'opérateur n'est pas encore prêt, vérifier les logs"

    echo ""
    echo "=== Logs ==="
    kubectl logs -n "${NAMESPACE}" -l app=cost-operator --tail=50
}

# Afficher le statut
show_status() {
    log_info "Statut du déploiement:"

    kubectl get all -n "${NAMESPACE}" -l app=cost-operator

    echo ""
    log_info "Pour voir les logs: kubectl logs -n ${NAMESPACE} -l app=cost-operator -f"
    log_info "Pour supprimer: helm uninstall ${RELEASE_NAME} -n ${NAMESPACE}"
}

# Menu principal
main() {
    echo "=========================================="
    echo "  K8s Cost Operator - GitOps Deployment"
    echo "=========================================="
    echo ""

    local action="${1:-deploy}"

    case "${action}" in
        build)
            check_prerequisites
            local image=$(build_image)
            echo ""
            echo "Image: ${image}"
            ;;
        push)
            check_prerequisites
            local image="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
            push_image "${image}"
            ;;
        deploy)
            check_prerequisites
            local full_image="${REGISTRY}/${IMAGE_NAME}:${VERSION}"

            # Build
            build_image

            # Push
            push_image "${full_image}"

            # Deploy
            deploy_helm

            # Verify
            verify_deployment

            show_status

            log_success "Déploiement terminé!"
            ;;
        verify)
            verify_deployment
            ;;
        status)
            show_status
            ;;
        delete)
            log_info "Suppression du déploiement..."
            helm uninstall "${RELEASE_NAME}" -n "${NAMESPACE}" || true
            kubectl delete namespace "${NAMESPACE}" || true
            log_success "Nettoyage terminé"
            ;;
        *)
            echo "Usage: $0 {build|push|deploy|verify|status|delete}"
            echo ""
            echo "Commandes:"
            echo "  build   - Construire l'image Docker"
            echo "  push    - Pousser l'image vers le registry"
            echo "  deploy  - Build + Push + Déployer (complet)"
            echo "  verify  - Vérifier le déploiement"
            echo "  status  - Afficher le statut"
            echo "  delete  - Supprimer le déploiement"
            echo ""
            echo "Variables d'environnement:"
            echo "  VERSION      - Tag de l'image (défaut: 1.0.0)"
            echo "  NAMESPACE    - Namespace de déploiement (défaut: cost-operator)"
            echo "  GHCR_TOKEN   - Token pour GHCR.io"
            echo "  GHCR_USER    - Utilisateur GHCR.io"
            exit 1
            ;;
    esac
}

main "$@"