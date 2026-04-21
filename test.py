"""
Script de test pour valider le fonctionnement de l'opérateur
"""

import sys
import logging
from metrics import MetricsCollector
from analyzer import CostAnalyzer
from report import ReportGenerator

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_metrics_collector():
    """Test la collecte des métriques"""
    print("🧪 Test 1: Collecte des métriques")
    print("-" * 50)
    
    try:
        collector = MetricsCollector(prometheus_url=None)  # Utilise metrics-server
        
        # Test de parsing CPU
        cpu_100m = collector._parse_cpu("100m")
        assert cpu_100m == 0.1, f"Parsing CPU échoué: {cpu_100m}"
        print("  ✅ Parsing CPU: 100m = 0.1 cores")
        
        # Test de parsing mémoire
        memory_512mi = collector._parse_memory("512Mi")
        assert memory_512mi == 512, f"Parsing mémoire échoué: {memory_512mi}"
        print("  ✅ Parsing mémoire: 512Mi = 512 MiB")
        
        memory_1gi = collector._parse_memory("1Gi")
        assert memory_1gi == 1024, f"Parsing mémoire échoué: {memory_1gi}"
        print("  ✅ Parsing mémoire: 1Gi = 1024 MiB")
        
        print("✅ Collecte des métriques: PASSED\n")
        return True
    
    except Exception as e:
        print(f"❌ Collecte des métriques: FAILED - {e}\n")
        return False


def test_analyzer():
    """Test l'analyseur"""
    print("🧪 Test 2: Analyseur")
    print("-" * 50)
    
    try:
        # Mock d'une métrique collecteur
        collector = MetricsCollector(prometheus_url=None)
        analyzer = CostAnalyzer(collector)
        
        # Teste le calcul du score d'optimisation
        score = analyzer.calculate_optimization_score()
        assert 0 <= score <= 100, f"Score invalide: {score}"
        print(f"  ✅ Score d'optimisation: {score}%")
        
        # Teste les économies totales
        savings = analyzer.calculate_total_savings()
        assert savings >= 0, f"Économies invalides: {savings}"
        print(f"  ✅ Économies totales: €{savings:.2f}/mois")
        
        print("✅ Analyseur: PASSED\n")
        return True
    
    except Exception as e:
        print(f"❌ Analyseur: FAILED - {e}\n")
        return False


def test_report_generator():
    """Test la génération de rapport"""
    print("🧪 Test 3: Génération de rapport")
    print("-" * 50)
    
    try:
        collector = MetricsCollector(prometheus_url=None)
        analyzer = CostAnalyzer(collector)
        generator = ReportGenerator(analyzer)
        
        # Génère le HTML
        html = generator.generate_html(cluster_name="test-cluster")
        
        # Vérifie que c'est du HTML valide
        assert "<html" in html.lower(), "HTML invalide"
        assert "cost-optimization" in html.lower() or "kubernetes" in html.lower(), \
            "Contenu HTML invalide"
        
        print(f"  ✅ Rapport HTML généré: {len(html)} bytes")
        
        # Essaie de sauvegarder
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False) as f:
                f.write(html)
                filepath = f.name
            print(f"  ✅ Rapport sauvegardé: {filepath}")
        except Exception as e:
            print(f"  ⚠️  Sauvegarde non testée: {e}")
        
        print("✅ Génération de rapport: PASSED\n")
        return True
    
    except Exception as e:
        print(f"❌ Génération de rapport: FAILED - {e}\n")
        return False


def test_data_structures():
    """Test les structures de données"""
    print("🧪 Test 4: Structures de données")
    print("-" * 50)
    
    try:
        from analyzer import Recommendation
        
        # Crée une recommandation
        rec = Recommendation(
            workload_name="test-pod",
            namespace="default",
            workload_type="pod",
            optimization_type="cpu_reduction",
            current_cpu_request=0.5,
            recommended_cpu_request=0.1,
            current_memory_request=512,
            recommended_memory_request=256,
            estimated_savings_percent=50.0,
            reasoning="Test"
        )
        
        # Convertit en dict
        rec_dict = rec.to_dict()
        assert rec_dict['workload_name'] == "test-pod", "Conversion échouée"
        print(f"  ✅ Recommandation créée et convertie")
        
        print("✅ Structures de données: PASSED\n")
        return True
    
    except Exception as e:
        print(f"❌ Structures de données: FAILED - {e}\n")
        return False


def run_all_tests():
    """Exécute tous les tests"""
    print("\n")
    print("=" * 60)
    print("🧪 Tests du K8s Cost Optimization Operator")
    print("=" * 60)
    print("\n")
    
    results = {
        "Collecte des métriques": test_metrics_collector(),
        "Analyseur": test_analyzer(),
        "Génération de rapport": test_report_generator(),
        "Structures de données": test_data_structures(),
    }
    
    print("=" * 60)
    print("📊 Résumé des tests")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
    
    print(f"\nRésultat: {passed}/{total} tests réussis")
    
    if passed == total:
        print("\n🎉 Tous les tests sont passés!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) échoué(s)")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
