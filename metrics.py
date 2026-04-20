"""
Module de collecte des métriques depuis Prometheus ou metrics-server
"""

import logging
from typing import Dict, List, Tuple, Optional
import requests
from datetime import datetime, timedelta
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collecte les métriques CPU/mémoire depuis Prometheus ou metrics-server"""

    def __init__(self, prometheus_url: Optional[str] = None):
        """
        Initialise le collecteur de métriques
        
        Args:
            prometheus_url: URL de Prometheus (ex: http://prometheus:9090)
                           Si None, utilise metrics-server
        """
        self.prometheus_url = prometheus_url
        self.use_prometheus = prometheus_url is not None
        
        try:
            config.load_incluster_config()
        except config.config_exception.ConfigException:
            config.load_kube_config()
        
        self.v1 = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
        
    def get_pod_metrics(self, namespace: str = None) -> Dict[str, Dict[str, float]]:
        """
        Récupère les métriques CPU/mémoire des pods
        
        Returns:
            Dict: {namespace/pod_name: {cpu_usage, memory_usage, cpu_request, cpu_limit, memory_request, memory_limit}}
        """
        if self.use_prometheus:
            return self._get_metrics_from_prometheus(namespace)
        else:
            return self._get_metrics_from_metrics_server(namespace)
    
    def _get_metrics_from_prometheus(self, namespace: str = None) -> Dict[str, Dict[str, float]]:
        """Récupère les métriques de Prometheus"""
        metrics = {}
        
        try:
            # Requête pour CPU
            cpu_query = 'rate(container_cpu_usage_seconds_total{pod!=""}[5m])'
            if namespace:
                cpu_query += f'{{namespace="{namespace}"}}'
            
            cpu_response = self._query_prometheus(cpu_query)
            
            # Requête pour Mémoire
            memory_query = 'container_memory_usage_bytes{pod!=""}'
            if namespace:
                memory_query += f'{{namespace="{namespace}"}}'
            
            memory_response = self._query_prometheus(memory_query)
            
            # Traiter les résultats CPU
            for result in cpu_response.get('data', {}).get('result', []):
                labels = result['metric']
                pod_key = f"{labels.get('namespace', 'default')}/{labels.get('pod', labels.get('pod_name', ''))}"
                if pod_key not in metrics:
                    metrics[pod_key] = {}
                metrics[pod_key]['cpu_usage'] = float(result['value'][1])
            
            # Traiter les résultats Mémoire
            for result in memory_response.get('data', {}).get('result', []):
                labels = result['metric']
                pod_key = f"{labels.get('namespace', 'default')}/{labels.get('pod', labels.get('pod_name', ''))}"
                if pod_key not in metrics:
                    metrics[pod_key] = {}
                memory_bytes = float(result['value'][1])
                metrics[pod_key]['memory_usage'] = memory_bytes / (1024 ** 2)  # Convertir en MiB
            
            logger.info(f"Collecté {len(metrics)} pods depuis Prometheus")
            
        except Exception as e:
            logger.error(f"Erreur lors de la collecte Prometheus: {e}")
        
        return metrics
    
    def _query_prometheus(self, query: str) -> Dict:
        """Exécute une requête Prometheus"""
        try:
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={'query': query},
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Erreur requête Prometheus: {e}")
            return {'data': {'result': []}}
    
    def _get_metrics_from_metrics_server(self, namespace: str = None) -> Dict[str, Dict[str, float]]:
        """Récupère les métriques depuis metrics-server (fallback)"""
        metrics = {}
        
        try:
            pods = self.v1.list_namespaced_pod(namespace=namespace or "default")
            
            for pod in pods.items:
                pod_namespace = pod.metadata.namespace
                pod_name = pod.metadata.name
                pod_key = f"{pod_namespace}/{pod_name}"
                
                metrics[pod_key] = {}
                
                # Récupère les requests/limits du manifeste
                for container in pod.spec.containers:
                    resources = container.resources or {}
                    requests = resources.requests or {}
                    limits = resources.limits or {}
                    
                    if requests.get('cpu'):
                        metrics[pod_key]['cpu_request'] = self._parse_cpu(requests['cpu'])
                    if limits.get('cpu'):
                        metrics[pod_key]['cpu_limit'] = self._parse_cpu(limits['cpu'])
                    if requests.get('memory'):
                        metrics[pod_key]['memory_request'] = self._parse_memory(requests['memory'])
                    if limits.get('memory'):
                        metrics[pod_key]['memory_limit'] = self._parse_memory(limits['memory'])
            
            logger.info(f"Collecté {len(metrics)} pods depuis metrics-server")
            
        except ApiException as e:
            logger.error(f"Erreur API Kubernetes: {e}")
        
        return metrics
    
    def get_pod_requests_limits(self, namespace: str = None) -> Dict[str, Dict[str, float]]:
        """
        Récupère les requests et limits CPU/mémoire des pods
        
        Returns:
            Dict: {namespace/pod_name: {cpu_request, cpu_limit, memory_request, memory_limit}}
        """
        requests_limits = {}
        
        try:
            namespaces = [namespace] if namespace else [ns.metadata.name for ns in self.v1.list_namespace().items]
            
            for ns in namespaces:
                pods = self.v1.list_namespaced_pod(namespace=ns)
                
                for pod in pods.items:
                    pod_key = f"{pod.metadata.namespace}/{pod.metadata.name}"
                    requests_limits[pod_key] = {
                        'cpu_request': 0,
                        'cpu_limit': 0,
                        'memory_request': 0,
                        'memory_limit': 0,
                        'containers': []
                    }
                    
                    for container in pod.spec.containers:
                        resources = container.resources or {}
                        req = resources.requests or {}
                        lim = resources.limits or {}
                        
                        container_info = {'name': container.name}
                        
                        if req.get('cpu'):
                            cpu_value = self._parse_cpu(req['cpu'])
                            requests_limits[pod_key]['cpu_request'] += cpu_value
                            container_info['cpu_request'] = cpu_value
                        
                        if lim.get('cpu'):
                            cpu_value = self._parse_cpu(lim['cpu'])
                            requests_limits[pod_key]['cpu_limit'] += cpu_value
                            container_info['cpu_limit'] = cpu_value
                        
                        if req.get('memory'):
                            mem_value = self._parse_memory(req['memory'])
                            requests_limits[pod_key]['memory_request'] += mem_value
                            container_info['memory_request'] = mem_value
                        
                        if lim.get('memory'):
                            mem_value = self._parse_memory(lim['memory'])
                            requests_limits[pod_key]['memory_limit'] += mem_value
                            container_info['memory_limit'] = mem_value
                        
                        requests_limits[pod_key]['containers'].append(container_info)
            
            logger.info(f"Collecté {len(requests_limits)} pods avec requests/limits")
            
        except ApiException as e:
            logger.error(f"Erreur API Kubernetes: {e}")
        
        return requests_limits
    
    def get_deployment_replicas(self, namespace: str = None) -> Dict[str, Dict]:
        """
        Récupère les informations des déploiements (replicas, desired, etc)
        
        Returns:
            Dict: {namespace/deployment_name: {current_replicas, desired_replicas, ready_replicas}}
        """
        deployments = {}
        
        try:
            apps_v1 = client.AppsV1Api()
            namespaces = [namespace] if namespace else [ns.metadata.name for ns in self.v1.list_namespace().items]
            
            for ns in namespaces:
                deploys = apps_v1.list_namespaced_deployment(namespace=ns)
                
                for deploy in deploys.items:
                    deploy_key = f"{deploy.metadata.namespace}/{deploy.metadata.name}"
                    status = deploy.status
                    
                    deployments[deploy_key] = {
                        'desired_replicas': deploy.spec.replicas or 1,
                        'current_replicas': status.replicas or 0,
                        'ready_replicas': status.ready_replicas or 0,
                        'updated_replicas': status.updated_replicas or 0,
                        'labels': deploy.spec.selector.match_labels or {}
                    }
            
            logger.info(f"Collecté {len(deployments)} déploiements")
            
        except ApiException as e:
            logger.error(f"Erreur API Kubernetes: {e}")
        
        return deployments
    
    @staticmethod
    def _parse_cpu(cpu_str: str) -> float:
        """
        Parse une valeur CPU (ex: "100m" -> 0.1, "1" -> 1.0)
        
        Returns:
            float: CPU en cores
        """
        if cpu_str.endswith('m'):
            return float(cpu_str[:-1]) / 1000
        else:
            return float(cpu_str)
    
    @staticmethod
    def _parse_memory(memory_str: str) -> float:
        """
        Parse une valeur mémoire et convertit en MiB
        
        Examples:
            "512Mi" -> 512
            "1Gi" -> 1024
            "512M" -> 500 (approx)
        """
        multipliers = {
            'Ki': 1 / 1024,
            'Mi': 1,
            'Gi': 1024,
            'Ti': 1024 ** 2,
            'K': 1 / 1000 / 1024,
            'M': 1 / 1000,
            'G': 1000,
            'T': 1000 ** 2,
        }
        
        for suffix, multiplier in multipliers.items():
            if memory_str.endswith(suffix):
                return float(memory_str[:-len(suffix)]) * multiplier
        
        return float(memory_str)
    
    def get_idle_pods(self, threshold_cpu: float = 0.01, threshold_memory: float = 50) -> List[str]:
        """
        Identifie les pods "idle" (peu d'utilisation)
        
        Args:
            threshold_cpu: Seuil CPU en cores (défaut: 0.01 = 10m)
            threshold_memory: Seuil mémoire en MiB (défaut: 50)
        
        Returns:
            List: Pods considérés comme idle
        """
        idle_pods = []
        
        if not self.use_prometheus:
            logger.warning("Détection de pods idle nécessite Prometheus")
            return idle_pods
        
        metrics = self.get_pod_metrics()
        
        for pod_key, pod_metrics in metrics.items():
            cpu_usage = pod_metrics.get('cpu_usage', 0)
            memory_usage = pod_metrics.get('memory_usage', 0)
            
            if cpu_usage < threshold_cpu and memory_usage < threshold_memory:
                idle_pods.append(pod_key)
        
        logger.info(f"Détecté {len(idle_pods)} pods idle")
        return idle_pods
