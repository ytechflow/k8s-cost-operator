"""
Module d'analyse des optimisations possibles
"""

import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
from metrics import MetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class Recommendation:
    """Représente une recommandation d'optimisation"""
    workload_name: str
    namespace: str
    workload_type: str  # 'pod', 'deployment', etc
    optimization_type: str  # 'cpu_reduction', 'memory_reduction', 'scale_down', 'remove'
    current_cpu_request: float  # en cores
    recommended_cpu_request: float
    current_memory_request: float  # en MiB
    recommended_memory_request: float
    current_replicas: int = 1
    recommended_replicas: int = 1
    estimated_savings_percent: float = 0.0
    reasoning: str = ""
    priority: str = "medium"  # low, medium, high
    
    def to_dict(self):
        return asdict(self)


class CostAnalyzer:
    """Analyse les coûts et génère des recommandations d'optimisation"""
    
    # Facteurs de coût approximatifs ($/core/mois, $/GiB/mois)
    CPU_COST_PER_MONTH = 10  # $ par core/mois
    MEMORY_COST_PER_MONTH = 1  # $ par GiB/mois
    
    # Seuils d'analyse
    CPU_UTILIZATION_THRESHOLD = 0.3  # Si utilisation < 30%, surprovisionné
    MEMORY_UTILIZATION_THRESHOLD = 0.3
    CPU_THROTTLING_THRESHOLD = 0.9  # Si limite atteinte > 90%, sous-provisionné
    
    def __init__(self, metrics_collector: MetricsCollector):
        """
        Initialise l'analyseur
        
        Args:
            metrics_collector: Instance de MetricsCollector
        """
        self.metrics = metrics_collector
        self.recommendations: List[Recommendation] = []
    
    def analyze(self, namespace: str = None) -> List[Recommendation]:
        """
        Lance l'analyse complète
        
        Args:
            namespace: Namespace à analyser (None = tous)
        
        Returns:
            List[Recommendation]: Liste des recommandations
        """
        self.recommendations = []
        
        # Récupère les données
        pod_requests_limits = self.metrics.get_pod_requests_limits(namespace)
        pod_metrics = self.metrics.get_pod_metrics(namespace)
        deployments = self.metrics.get_deployment_replicas(namespace)
        idle_pods = self.metrics.get_idle_pods()
        
        # Analyse les pods
        for pod_key, rl in pod_requests_limits.items():
            if pod_key not in pod_metrics:
                continue
            
            pod_metrics_data = pod_metrics[pod_key]
            ns, pod_name = pod_key.split('/')
            
            # Détecte les pods idle
            if pod_key in idle_pods:
                self._analyze_idle_pod(pod_key, ns, pod_name, rl)
                continue
            
            # Détecte le surprovisionnement CPU
            self._analyze_cpu_surprovisioning(pod_key, ns, pod_name, rl, pod_metrics_data)
            
            # Détecte le surprovisionnement mémoire
            self._analyze_memory_surprovisioning(pod_key, ns, pod_name, rl, pod_metrics_data)
        
        # Analyse les déploiements
        for deploy_key, deploy_info in deployments.items():
            ns, deploy_name = deploy_key.split('/')
            self._analyze_deployment_replicas(deploy_key, ns, deploy_name, deploy_info)
        
        # Trie par priorité et économies potentielles
        self.recommendations.sort(
            key=lambda r: (r.priority == 'low', r.estimated_savings_percent),
            reverse=True
        )
        
        logger.info(f"Analyse complétée: {len(self.recommendations)} recommandations")
        return self.recommendations
    
    def _analyze_cpu_surprovisioning(
        self,
        pod_key: str,
        namespace: str,
        pod_name: str,
        requests_limits: Dict,
        metrics_data: Dict
    ):
        """Analyse le surprovisionnement CPU"""
        cpu_request = requests_limits.get('cpu_request', 0)
        cpu_usage = metrics_data.get('cpu_usage', 0)
        
        if cpu_request == 0:
            return
        
        utilization = cpu_usage / cpu_request if cpu_request > 0 else 0
        
        if utilization < self.CPU_UTILIZATION_THRESHOLD:
            # Recommande une réduction
            new_cpu_request = max(0.01, cpu_usage * 1.2)  # Ajoute 20% de marge
            savings = (cpu_request - new_cpu_request) * self.CPU_COST_PER_MONTH
            
            rec = Recommendation(
                workload_name=pod_name,
                namespace=namespace,
                workload_type='pod',
                optimization_type='cpu_reduction',
                current_cpu_request=cpu_request,
                recommended_cpu_request=new_cpu_request,
                current_memory_request=requests_limits.get('memory_request', 0),
                recommended_memory_request=requests_limits.get('memory_request', 0),
                estimated_savings_percent=((cpu_request - new_cpu_request) / cpu_request * 100),
                reasoning=f"CPU utilisé: {cpu_usage:.4f} cores ({utilization*100:.1f}%). "
                         f"Réduction possible de {cpu_request:.3f} à {new_cpu_request:.3f} cores",
                priority='high' if utilization < 0.1 else 'medium'
            )
            self.recommendations.append(rec)
            logger.debug(f"Recommandation CPU pour {pod_key}: {rec.reasoning}")
    
    def _analyze_memory_surprovisioning(
        self,
        pod_key: str,
        namespace: str,
        pod_name: str,
        requests_limits: Dict,
        metrics_data: Dict
    ):
        """Analyse le surprovisionnement mémoire"""
        memory_request = requests_limits.get('memory_request', 0)
        memory_usage = metrics_data.get('memory_usage', 0)
        
        if memory_request == 0:
            return
        
        utilization = memory_usage / memory_request if memory_request > 0 else 0
        
        if utilization < self.MEMORY_UTILIZATION_THRESHOLD:
            # Recommande une réduction
            new_memory_request = max(32, memory_usage * 1.15)  # Ajoute 15% de marge
            savings_percent = (memory_request - new_memory_request) / memory_request * 100
            
            rec = Recommendation(
                workload_name=pod_name,
                namespace=namespace,
                workload_type='pod',
                optimization_type='memory_reduction',
                current_cpu_request=requests_limits.get('cpu_request', 0),
                recommended_cpu_request=requests_limits.get('cpu_request', 0),
                current_memory_request=memory_request,
                recommended_memory_request=new_memory_request,
                estimated_savings_percent=savings_percent,
                reasoning=f"Mémoire utilisée: {memory_usage:.0f} MiB ({utilization*100:.1f}%). "
                         f"Réduction possible de {memory_request:.0f} à {new_memory_request:.0f} MiB",
                priority='high' if utilization < 0.15 else 'medium'
            )
            self.recommendations.append(rec)
            logger.debug(f"Recommandation mémoire pour {pod_key}: {rec.reasoning}")
    
    def _analyze_idle_pod(
        self,
        pod_key: str,
        namespace: str,
        pod_name: str,
        requests_limits: Dict
    ):
        """Analyse les pods idle"""
        cpu_request = requests_limits.get('cpu_request', 0)
        memory_request = requests_limits.get('memory_request', 0)
        total_savings = (cpu_request * self.CPU_COST_PER_MONTH +
                        memory_request / 1024 * self.MEMORY_COST_PER_MONTH)
        
        rec = Recommendation(
            workload_name=pod_name,
            namespace=namespace,
            workload_type='pod',
            optimization_type='remove',
            current_cpu_request=cpu_request,
            recommended_cpu_request=0,
            current_memory_request=memory_request,
            recommended_memory_request=0,
            estimated_savings_percent=100.0,
            reasoning="Pod idle détecté (consommation CPU et mémoire très faible). "
                     "Considérer la suppression ou le scale down.",
            priority='high'
        )
        self.recommendations.append(rec)
        logger.debug(f"Pod idle détecté: {pod_key}")
    
    def _analyze_deployment_replicas(
        self,
        deploy_key: str,
        namespace: str,
        deploy_name: str,
        deploy_info: Dict
    ):
        """Analyse les replicas de déploiement"""
        desired = deploy_info.get('desired_replicas', 1)
        ready = deploy_info.get('ready_replicas', 0)
        
        # Si des replicas ne sont jamais "ready", peut indiquer un problème
        if desired > 0 and ready < desired:
            failed_replicas = desired - ready
            rec = Recommendation(
                workload_name=deploy_name,
                namespace=namespace,
                workload_type='deployment',
                optimization_type='scale_down',
                current_cpu_request=0,
                recommended_cpu_request=0,
                current_memory_request=0,
                recommended_memory_request=0,
                current_replicas=desired,
                recommended_replicas=ready,
                estimated_savings_percent=(failed_replicas / desired * 100) if desired > 0 else 0,
                reasoning=f"Déploiement {desired} replicas désirés mais seulement {ready} ready. "
                         f"Possibilité de réduire ou investiguer les erreurs.",
                priority='medium'
            )
            self.recommendations.append(rec)
            logger.debug(f"Recommandation réplicas pour {deploy_key}: {rec.reasoning}")
    
    def get_recommendations_by_namespace(self) -> Dict[str, List[Recommendation]]:
        """Groupe les recommandations par namespace"""
        by_ns = {}
        for rec in self.recommendations:
            if rec.namespace not in by_ns:
                by_ns[rec.namespace] = []
            by_ns[rec.namespace].append(rec)
        return by_ns
    
    def get_recommendations_by_priority(self) -> Dict[str, List[Recommendation]]:
        """Groupe les recommandations par priorité"""
        by_priority = {'high': [], 'medium': [], 'low': []}
        for rec in self.recommendations:
            by_priority[rec.priority].append(rec)
        return by_priority
    
    def calculate_total_savings(self) -> float:
        """Calcule les économies potentielles totales en $/mois"""
        total = 0
        for rec in self.recommendations:
            cpu_savings = (rec.current_cpu_request - rec.recommended_cpu_request) * self.CPU_COST_PER_MONTH
            memory_savings = ((rec.current_memory_request - rec.recommended_memory_request) / 1024 *
                            self.MEMORY_COST_PER_MONTH)
            replica_savings = ((rec.current_replicas - rec.recommended_replicas) *
                             (rec.current_cpu_request * self.CPU_COST_PER_MONTH +
                              rec.current_memory_request / 1024 * self.MEMORY_COST_PER_MONTH))
            total += cpu_savings + memory_savings + replica_savings
        return total
    
    def calculate_optimization_score(self) -> float:
        """
        Calcule un score d'optimisation global (0-100)
        100 = parfaitement optimisé, 0 = très mal optimisé
        """
        if len(self.recommendations) == 0:
            return 100.0
        
        # Pénalité basée sur nombre et priorité des recommandations
        high_priority_count = sum(1 for r in self.recommendations if r.priority == 'high')
        medium_priority_count = sum(1 for r in self.recommendations if r.priority == 'medium')
        
        score = 100.0
        score -= high_priority_count * 5
        score -= medium_priority_count * 2
        
        return max(0, min(100, score))
