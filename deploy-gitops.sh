#!/bin/bash

set -euo pipefail

REGISTRY="${REGISTRY:-harbor.dev01.sayzx.fr}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-${REGISTRY}/admin/cost-operator}"
VERSION="${VERSION:-latest}"
NAMESPACE="${NAMESPACE:-cost-operator-system}"
RELEASE_NAME="${RELEASE_NAME:-cost-operator}"
HELM_CHART="./helm/cost-operator"

HARBOR_USER="${HARBOR_USER:-}"
HARBOR_PASSWORD="${HARBOR_PASSWORD:-}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

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

    if ! kubectl cluster-info >/dev/null 2>&1; then
        log_error "Pas de connexion au cluster Kubernetes"
        exit 1
    fi

    log_success "Prérequis vérifiés"
}

build_image() {
    local full_image="${IMAGE_REPOSITORY}:${VERSION}"

    log_info "Construction de l'image Docker..."
    docker build -t "${full_image}" .
    log_success "Image construite: ${full_image}"
}

push_image() {
    local full_image="$1"

    log_info "Push de l'image vers le registry..."

    if [ -n "${HARBOR_USER}" ] && [ -n "${HARBOR_PASSWORD}" ]; then
        docker login "${REGISTRY}" -u "${HARBOR_USER}" -p "${HARBOR_PASSWORD}"
    else
        log_warn "Aucun identifiant registry fourni, push tenté avec la session Docker courante"
    fi

    docker push "${full_image}"
    log_success "Image poussée: ${full_image}"
}

deploy_helm() {
    log_info "Déploiement Helm dans le namespace ${NAMESPACE}..."
    kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

    helm upgrade --install "${RELEASE_NAME}" "${HELM_CHART}" \
        --namespace "${NAMESPACE}" \
        --create-namespace \
        --wait \
        --timeout 5m \
        --set image.repository="${IMAGE_REPOSITORY}" \
        --set image.tag="${VERSION}"

    log_success "Opérateur déployé"
}

verify_deployment() {
    log_info "Vérification du déploiement..."

    echo ""
    echo "=== Pods ==="
    kubectl get pods -n "${NAMESPACE}" -l app.kubernetes.io/instance="${RELEASE_NAME}"

    echo ""
    echo "=== Services ==="
    kubectl get svc -n "${NAMESPACE}"

    echo ""
    echo "=== ConfigMaps ==="
    kubectl get configmap -n "${NAMESPACE}"

    echo ""
    echo "=== CRD ==="
    kubectl get crd costreports.cost.k8s.io 2>/dev/null || echo "CRD non trouvée"

    log_info "Attente du démarrage de l'opérateur..."
    kubectl wait --for=condition=ready pod -l app.kubernetes.io/instance="${RELEASE_NAME}" -n "${NAMESPACE}" --timeout=120s 2>/dev/null && \
        log_success "Opérateur prêt!" || \
        log_warn "L'opérateur n'est pas encore prêt, vérifier les logs"

    echo ""
    echo "=== Logs ==="
    kubectl logs -n "${NAMESPACE}" -l app.kubernetes.io/instance="${RELEASE_NAME}" --tail=50
}

show_status() {
    log_info "Statut du déploiement:"
    kubectl get all -n "${NAMESPACE}" -l app.kubernetes.io/instance="${RELEASE_NAME}"
    echo ""
    log_info "Pour voir les logs: kubectl logs -n ${NAMESPACE} -l app.kubernetes.io/instance=${RELEASE_NAME} -f"
    log_info "Pour supprimer: helm uninstall ${RELEASE_NAME} -n ${NAMESPACE}"
}

main() {
    echo "=========================================="
    echo "  K8s Cost Operator - GitOps Deployment"
    echo "=========================================="
    echo ""

    local action="${1:-deploy}"

    case "${action}" in
        build)
            check_prerequisites
            build_image
            ;;
        push)
            check_prerequisites
            push_image "${IMAGE_REPOSITORY}:${VERSION}"
            ;;
        deploy)
            check_prerequisites
            build_image
            push_image "${IMAGE_REPOSITORY}:${VERSION}"
            deploy_helm
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
            echo "Variables d'environnement:"
            echo "  VERSION          - Tag de l'image (défaut: latest)"
            echo "  NAMESPACE        - Namespace de déploiement (défaut: cost-operator-system)"
            echo "  RELEASE_NAME     - Nom du release Helm (défaut: cost-operator)"
            echo "  IMAGE_REPOSITORY - Repository complet de l'image"
            echo "  REGISTRY         - Registry Docker (utilisé si IMAGE_REPOSITORY est absent)"
            echo "  HARBOR_USER      - Utilisateur registry optionnel"
            echo "  HARBOR_PASSWORD  - Mot de passe registry optionnel"
            exit 1
            ;;
    esac
}

main "$@"