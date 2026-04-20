"""
Exemple d'utilisation de l'opérateur en mode local
"""

import logging
from metrics import MetricsCollector
from analyzer import CostAnalyzer, Recommendation
from report import ReportGenerator
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Exemple d'utilisation complet"""
    
    logger.info("=" * 60)
    logger.info("Exemple d'utilisation du Cost Optimizer")
    logger.info("=" * 60)
    
    # 1. Collecte des métriques
    logger.info("\n1️⃣  Collecte des métriques...")
    collector = MetricsCollector(prometheus_url=None)
    
    try:
        # Essaie de récupérer les métriques du cluster
        pod_metrics = collector.get_pod_metrics()
        logger.info(f"   Pods collectés: {len(pod_metrics)}")
        
        requests_limits = collector.get_pod_requests_limits()
        logger.info(f"   Requests/limits collectés: {len(requests_limits)}")
        
        deployments = collector.get_deployment_replicas()
        logger.info(f"   Déploiements collectés: {len(deployments)}")
        
    except Exception as e:
        logger.warning(f"   ⚠️  Impossible de se connecter à Kubernetes: {e}")
        logger.info("   (C'est normal en mode test sans cluster)")
    
    # 2. Analyse
    logger.info("\n2️⃣  Analyse des optimisations...")
    analyzer = CostAnalyzer(collector)
    
    # Crée quelques recommandations de test
    test_recommendations = [
        Recommendation(
            workload_name="nginx-deployment",
            namespace="production",
            workload_type="pod",
            optimization_type="cpu_reduction",
            current_cpu_request=1.0,
            recommended_cpu_request=0.3,
            current_memory_request=512,
            recommended_memory_request=512,
            estimated_savings_percent=70.0,
            reasoning="CPU utilisé en moyenne 0.2 cores (20%). "
                     "Peut être réduit à 0.3 cores (30% marge).",
            priority="high"
        ),
        Recommendation(
            workload_name="redis-cache",
            namespace="production",
            workload_type="pod",
            optimization_type="memory_reduction",
            current_cpu_request=0.5,
            recommended_cpu_request=0.5,
            current_memory_request=2048,
            recommended_memory_request=512,
            estimated_savings_percent=75.0,
            reasoning="Mémoire utilisée: ~300 MiB (15% du request). "
                     "Peut être réduite à 512 MiB.",
            priority="high"
        ),
        Recommendation(
            workload_name="idle-worker",
            namespace="staging",
            workload_type="pod",
            optimization_type="remove",
            current_cpu_request=0.1,
            recommended_cpu_request=0,
            current_memory_request=256,
            recommended_memory_request=0,
            estimated_savings_percent=100.0,
            reasoning="Pod idle détecté (CPU < 5m, mémoire < 10 MiB). "
                     "Recommande la suppression.",
            priority="high"
        ),
        Recommendation(
            workload_name="api-service",
            namespace="production",
            workload_type="deployment",
            optimization_type="scale_down",
            current_cpu_request=0.5,
            recommended_cpu_request=0.5,
            current_memory_request=512,
            recommended_memory_request=512,
            current_replicas=5,
            recommended_replicas=3,
            estimated_savings_percent=40.0,
            reasoning="2 replicas sont jamais en état 'ready'. "
                     "Peut être réduit à 3 replicas.",
            priority="medium"
        ),
    ]
    
    analyzer.recommendations = test_recommendations
    
    logger.info(f"   Recommandations: {len(analyzer.recommendations)}")
    logger.info(f"   Économies potentielles: ${analyzer.calculate_total_savings():.2f}/mois")
    logger.info(f"   Score d'optimisation: {analyzer.calculate_optimization_score():.1f}%")
    
    # 3. Génération du rapport
    logger.info("\n3️⃣  Génération du rapport HTML...")
    generator = ReportGenerator(analyzer)
    html = generator.generate_html(cluster_name="production-cluster")
    
    logger.info(f"   Rapport généré: {len(html)} bytes")
    
    # 4. Sauvegarde
    logger.info("\n4️⃣  Sauvegarde du rapport...")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filepath = f"cost-report-example-{timestamp}.html"
    
    try:
        generator.save_to_file(filepath, cluster_name="production-cluster")
        logger.info(f"   ✅ Rapport sauvegardé: {filepath}")
        logger.info(f"   📂 Ouvrir le fichier: file://{filepath}")
    except Exception as e:
        logger.error(f"   ❌ Erreur lors de la sauvegarde: {e}")
    
    # 5. Afficher les recommandations
    logger.info("\n5️⃣  Détails des recommandations:")
    for priority in ['high', 'medium', 'low']:
        recs = [r for r in analyzer.recommendations if r.priority == priority]
        if recs:
            logger.info(f"\n   {priority.upper()}:")
            for rec in recs:
                logger.info(f"     • {rec.workload_name} ({rec.namespace})")
                logger.info(f"       Type: {rec.optimization_type}")
                logger.info(f"       Économies: {rec.estimated_savings_percent:.1f}%")
    
    # 6. Résumé par namespace
    logger.info("\n6️⃣  Résumé par namespace:")
    by_ns = analyzer.get_recommendations_by_namespace()
    for ns, recs in by_ns.items():
        total_savings = sum(r.estimated_savings_percent for r in recs) / len(recs) if recs else 0
        logger.info(f"   {ns}: {len(recs)} recommandations, "
                   f"économies moyennes: {total_savings:.1f}%")
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ Exemple terminé!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
