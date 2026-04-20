"""
Opérateur Kubernetes pour l'optimisation des coûts
Utilise kopf pour gérer la CRD CostReport
"""

import kopf
import logging
import os
from datetime import datetime
from typing import Dict, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException

from metrics import MetricsCollector
from analyzer import CostAnalyzer
from report import ReportGenerator

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration de Kubernetes
try:
    config.load_incluster_config()
except config.config_exception.ConfigException:
    config.load_kube_config()

v1 = client.CoreV1Api()
custom_api = client.CustomObjectsApi()


@kopf.on.event(
    "v1",
    "costreports",
    group="cost.k8s.io",
    annotations={"cost.k8s.io/watch": "true"},
)
def log_costreport_event(event, **kwargs):
    """Log les événements de CostReport (debugging)"""
    logger.debug(f"Événement CostReport: {event}")


@kopf.on.create("cost.k8s.io", "v1", "costreports")
def create_costreport(spec, name, namespace, **kwargs):
    """
    Crée un nouveau rapport quand une CRD CostReport est créée
    """
    logger.info(f"CostReport créé: {namespace}/{name}")
    
    # Exécute l'analyse immédiatement
    _run_analysis(spec, name, namespace)
    
    return {"status": "initial_report_generated"}


@kopf.on.update("cost.k8s.io", "v1", "costreports")
def update_costreport(spec, name, namespace, **kwargs):
    """
    Met à jour le rapport quand une CRD CostReport est modifiée
    """
    logger.info(f"CostReport mis à jour: {namespace}/{name}")
    
    # Exécute l'analyse
    _run_analysis(spec, name, namespace)
    
    return {"status": "report_updated"}


@kopf.timer(
    "cost.k8s.io", "v1", "costreports",
    interval=3600,  # Exécute toutes les heures
)
def periodic_analysis(spec, name, namespace, **kwargs):
    """
    Génère périodiquement des rapports selon le schedule
    """
    logger.info(f"Analyse périodique: {namespace}/{name}")
    
    # Vérifie le schedule (si défini)
    schedule = spec.get("schedule", "* * * * *")  # Default: toutes les heures
    
    try:
        _run_analysis(spec, name, namespace)
    except Exception as e:
        logger.error(f"Erreur lors de l'analyse périodique: {e}")
        return {"status": "error", "error": str(e)}
    
    return {"status": "periodic_analysis_completed"}


def _run_analysis(spec: Dict, name: str, namespace: str):
    """
    Exécute l'analyse complète et génère le rapport
    
    Args:
        spec: Spécification de la CRD CostReport
        name: Nom du CostReport
        namespace: Namespace du CostReport
    """
    try:
        logger.info(f"Démarrage de l'analyse pour {namespace}/{name}")
        
        # Configuration
        scope = spec.get("scope", "cluster")  # "cluster" ou "namespace"
        output_type = spec.get("output", "configmap")  # "configmap" ou "file"
        output_path = spec.get("outputPath", "/tmp")
        auto_apply = spec.get("autoApply", False)
        prometheus_url = spec.get("prometheusUrl", None)
        cluster_name = spec.get("clusterName", "kubernetes")
        
        # Détermine le scope d'analyse
        analysis_namespace = namespace if scope == "namespace" else None
        
        # Collecte les métriques
        logger.info("Collecte des métriques...")
        metrics_collector = MetricsCollector(prometheus_url=prometheus_url)
        
        # Analyse
        logger.info("Analyse des optimisations...")
        analyzer = CostAnalyzer(metrics_collector)
        recommendations = analyzer.analyze(namespace=analysis_namespace)
        
        logger.info(f"Analyse complétée: {len(recommendations)} recommandations")
        
        # Génère le rapport
        logger.info("Génération du rapport HTML...")
        report_generator = ReportGenerator(analyzer)
        
        # Génère le rapport
        if output_type == "file":
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            filepath = f"{output_path}/cost-report-{name}-{timestamp}.html"
            report_generator.save_to_file(filepath, cluster_name)
            logger.info(f"Rapport sauvegardé en fichier: {filepath}")
            
            # Crée un ConfigMap pointant vers le fichier
            _create_report_status_configmap(name, namespace, {
                "filepath": filepath,
                "timestamp": timestamp,
                "status": "completed"
            })
        
        else:  # output_type == "configmap"
            html_report = report_generator.generate_html(cluster_name)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            configmap_name = f"cost-report-{name}-{timestamp}"
            
            _save_report_to_configmap(namespace, configmap_name, html_report)
            logger.info(f"Rapport sauvegardé en ConfigMap: {configmap_name}")
            
            # Crée un ConfigMap de statut
            _create_report_status_configmap(name, namespace, {
                "configmap_name": configmap_name,
                "timestamp": timestamp,
                "recommendations_count": len(recommendations),
                "total_savings": f"${analyzer.calculate_total_savings():.2f}",
                "optimization_score": f"{analyzer.calculate_optimization_score():.1f}%",
                "status": "completed"
            })
        
        # Applique les recommandations si auto_apply=true
        if auto_apply and recommendations:
            logger.info("Mode auto_apply activé, application des recommandations...")
            _apply_recommendations(recommendations)
        
        # Met à jour le statut du CostReport
        _update_costreport_status(name, namespace, {
            "lastAnalysis": datetime.now().isoformat(),
            "status": "completed",
            "recommendations": len(recommendations),
            "totalSavings": f"${analyzer.calculate_total_savings():.2f}",
            "optimizationScore": f"{analyzer.calculate_optimization_score():.1f}%"
        })
        
        logger.info(f"Analyse terminée pour {namespace}/{name}")
        
    except Exception as e:
        logger.error(f"Erreur lors de l'analyse: {e}", exc_info=True)
        _update_costreport_status(name, namespace, {
            "status": "error",
            "error": str(e)
        })
        raise


def _save_report_to_configmap(namespace: str, configmap_name: str, html_content: str):
    """
    Sauvegarde le rapport HTML dans un ConfigMap
    
    Args:
        namespace: Namespace du ConfigMap
        configmap_name: Nom du ConfigMap
        html_content: Contenu HTML du rapport
    """
    try:
        # Crée ou met à jour le ConfigMap
        configmap = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": configmap_name,
                "namespace": namespace,
                "labels": {
                    "app": "cost-optimization-operator",
                    "type": "cost-report"
                }
            },
            "data": {
                "report.html": html_content
            }
        }
        
        # Essaie de mettre à jour le ConfigMap existant
        try:
            v1.patch_namespaced_config_map(configmap_name, namespace, configmap)
            logger.info(f"ConfigMap {configmap_name} mis à jour")
        except ApiException as e:
            if e.status == 404:
                # ConfigMap n'existe pas, le crée
                v1.create_namespaced_config_map(namespace, configmap)
                logger.info(f"ConfigMap {configmap_name} créé")
            else:
                raise
    
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde en ConfigMap: {e}")
        raise


def _create_report_status_configmap(report_name: str, namespace: str, status_data: Dict):
    """
    Crée un ConfigMap de statut du rapport
    
    Args:
        report_name: Nom du rapport
        namespace: Namespace
        status_data: Données de statut
    """
    try:
        configmap_name = f"cost-report-status-{report_name}"
        
        configmap = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": configmap_name,
                "namespace": namespace,
                "labels": {
                    "app": "cost-optimization-operator",
                    "type": "cost-report-status"
                }
            },
            "data": {key: str(value) for key, value in status_data.items()}
        }
        
        try:
            v1.patch_namespaced_config_map(configmap_name, namespace, configmap)
        except ApiException as e:
            if e.status == 404:
                v1.create_namespaced_config_map(namespace, configmap)
        
        logger.info(f"ConfigMap de statut créé: {configmap_name}")
    
    except Exception as e:
        logger.error(f"Erreur lors de la création du ConfigMap de statut: {e}")


def _update_costreport_status(name: str, namespace: str, status: Dict):
    """
    Met à jour le statut du CostReport
    
    Args:
        name: Nom du CostReport
        namespace: Namespace du CostReport
        status: Dict avec les statuts à mettre à jour
    """
    try:
        # Récupère le CostReport actuel
        costreport = custom_api.get_namespaced_custom_object(
            "cost.k8s.io",
            "v1",
            namespace,
            "costreports",
            name
        )
        
        # Met à jour le statut
        costreport['status'] = status
        
        # Patche l'objet
        custom_api.patch_namespaced_custom_object(
            "cost.k8s.io",
            "v1",
            namespace,
            "costreports",
            name,
            costreport
        )
        
        logger.info(f"Statut du CostReport {name} mis à jour")
    
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour du statut: {e}")


def _apply_recommendations(recommendations: list):
    """
    Applique les recommandations (mode auto_apply)
    
    Note: Cette fonction est un placeholder pour la logique d'application
    des recommandations. Elle nécessite une validation et une approche prudente.
    
    Args:
        recommendations: Liste des recommandations
    """
    logger.warning("Mode auto_apply activé - application prudente des recommandations")
    
    try:
        apps_v1 = client.AppsV1Api()
        
        for rec in recommendations:
            if rec.optimization_type == "scale_down":
                # Scale down des déploiements
                deploy_name = rec.workload_name
                namespace = rec.namespace
                new_replicas = rec.recommended_replicas
                
                try:
                    deploy = apps_v1.read_namespaced_deployment(deploy_name, namespace)
                    deploy.spec.replicas = new_replicas
                    apps_v1.patch_namespaced_deployment(deploy_name, namespace, deploy)
                    logger.info(f"Scale down appliqué: {namespace}/{deploy_name} -> {new_replicas} replicas")
                except Exception as e:
                    logger.error(f"Erreur lors du scale down: {e}")
            
            # Note: Les modifications de CPU/mémoire requests/limits nécessitent une recréation des pods
            # Ce qui est plus complexe et nécessite une validation manuelle dans les cas réels
    
    except Exception as e:
        logger.error(f"Erreur lors de l'application des recommandations: {e}")


if __name__ == "__main__":
    logger.info("Démarrage de l'opérateur K8s Cost Optimization")
    kopf.run()
