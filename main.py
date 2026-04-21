"""
Opérateur Kubernetes pour l'optimisation des coûts
Utilise kopf pour gérer la CRD CostReport
"""

import kopf
import logging
import os
import json
import threading
from datetime import datetime
from typing import Dict, Optional, List
from urllib.parse import urlparse
from http.server import BaseHTTPRequestHandler, HTTPServer
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

HTTP_HOST = os.getenv("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.getenv("HTTP_PORT", "8080"))


def _list_namespaces() -> List[str]:
    """Retourne la liste des namespaces accessibles."""
    try:
        namespaces = [ns.metadata.name for ns in v1.list_namespace().items]
        return sorted(namespaces)
    except Exception as exc:
        logger.error(f"Erreur de lecture des namespaces: {exc}")
        return []


def _default_exclude_namespaces() -> List[str]:
    """Construit la liste des namespaces exclus pour les rapports globaux."""
    defaults = {
        "kube-system",
        "kube-public",
        "kube-node-lease",
        "cert-manager",
        "ingress-nginx",
        os.getenv("POD_NAMESPACE", "cost-operator-system"),
    }

    configured = os.getenv("EXCLUDE_NAMESPACES", "")
    for ns in configured.split(","):
        ns = ns.strip()
        if ns:
            defaults.add(ns)

    return sorted(defaults)


def _create_manual_costreport(scope: str, target_namespace: Optional[str] = None) -> Dict[str, str]:
    """Crée un CostReport manuel qui déclenchera une analyse immédiate via les handlers Kopf."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    cluster_name = os.getenv("CLUSTER_NAME", "kubernetes")
    prometheus_url = os.getenv("PROMETHEUS_URL", "").strip()

    if scope == "namespace":
        if not target_namespace:
            raise ValueError("namespace requis pour scope=namespace")
        report_name = f"manual-ns-{target_namespace}-{ts}"[:63]
        report_namespace = target_namespace
        exclude_namespaces = []
    else:
        report_name = f"manual-global-{ts}"[:63]
        report_namespace = "default"
        exclude_namespaces = _default_exclude_namespaces()

    spec = {
        "scope": scope,
        "schedule": "0 0 * * *",
        "output": "configmap",
        "outputPath": "/tmp",
        "autoApply": False,
        "clusterName": cluster_name,
        "excludeNamespaces": exclude_namespaces,
    }
    if prometheus_url:
        spec["prometheusUrl"] = prometheus_url

    body = {
        "apiVersion": "cost.k8s.io/v1",
        "kind": "CostReport",
        "metadata": {"name": report_name, "namespace": report_namespace},
        "spec": spec,
    }

    custom_api.create_namespaced_custom_object(
        "cost.k8s.io",
        "v1",
        report_namespace,
        "costreports",
        body,
    )

    return {
        "name": report_name,
        "namespace": report_namespace,
        "scope": scope,
        "status_configmap": f"cost-report-status-{report_name}",
    }


def _read_latest_report_statuses(limit: int = 50):
        """Récupère les ConfigMaps de statut des rapports pour alimenter le front."""
        reports = []
        try:
                configmaps = v1.list_config_map_for_all_namespaces(
                        label_selector="type=cost-report-status"
                )
        except Exception as exc:
                logger.error(f"Erreur de lecture des statuts de rapports: {exc}")
                return reports

        for item in configmaps.items:
                data = item.data or {}
                reports.append(
                        {
                                "name": item.metadata.name,
                                "namespace": item.metadata.namespace,
                                "report": data.get("configmap_name", ""),
                                "timestamp": data.get("timestamp", ""),
                                "recommendations": data.get("recommendations_count", ""),
                                "savings": data.get("total_savings", ""),
                                "score": data.get("optimization_score", ""),
                                "status": data.get("status", "unknown"),
                        }
                )

        reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return reports[:limit]


def _render_frontend_html() -> str:
        """Construit un front HTML léger pour visualiser les analyses récentes."""
        rows = []
        for report in _read_latest_report_statuses(limit=100):
                view_link = "-"
                if report["report"]:
                        view_link = (
                                f"<a href='/report/{report['namespace']}/{report['report']}'>"
                                "ouvrir le rapport"
                                "</a>"
                        )

                rows.append(
                        "<tr>"
                        f"<td>{report['namespace']}</td>"
                        f"<td>{report['name']}</td>"
                        f"<td>{report['timestamp'] or '-'}</td>"
                        f"<td>{report['status']}</td>"
                        f"<td>{report['recommendations'] or '-'}</td>"
                        f"<td>{report['savings'] or '-'}</td>"
                        f"<td>{report['score'] or '-'}</td>"
                        f"<td>{view_link}</td>"
                        "</tr>"
                )

        table_body = "".join(rows) or (
                "<tr><td colspan='8'>Aucun rapport trouvé pour le moment.</td></tr>"
        )

        return f"""<!doctype html>
<html lang='fr'>
<head>
    <meta charset='utf-8' />
    <meta name='viewport' content='width=device-width, initial-scale=1' />
    <title>Cost Operator Front</title>
    <style>
        :root {{
            --bg: #0b1320;
            --bg2: #111a2a;
            --card: #182437;
            --text: #e8f0ff;
            --muted: #9cb0d3;
            --accent: #1fc3a7;
            --border: #2a3b56;
        }}
        body {{
            margin: 0;
            font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
            color: var(--text);
            background: radial-gradient(circle at 10% 20%, #132746 0%, var(--bg) 40%), var(--bg2);
            min-height: 100vh;
        }}
        .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
        h1 {{ margin-bottom: 8px; }}
        p {{ color: var(--muted); margin-top: 0; }}
        .card {{
            background: color-mix(in oklab, var(--card), black 8%);
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
        }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ background: color-mix(in oklab, var(--card), black 15%); }}
        tr:hover td {{ background: color-mix(in oklab, var(--card), black 6%); }}
        a {{ color: var(--accent); text-decoration: none; }}
        .actions {{ margin-top: 20px; }}
        .actions h2 {{ font-size: 1.1rem; margin-bottom: 10px; }}
        .action-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 14px;
        }}
        .action-card {{
            padding: 14px;
            border-radius: 12px;
            border: 1px solid var(--border);
            background: color-mix(in oklab, var(--card), black 6%);
        }}
        .action-card h3 {{ margin-bottom: 8px; }}
        .action-card p {{ margin-bottom: 10px; font-size: 13px; }}
        button, select {{
            width: 100%;
            padding: 10px;
            border-radius: 10px;
            border: 1px solid var(--border);
            background: #0f1b2e;
            color: var(--text);
        }}
        button {{
            margin-top: 8px;
            background: var(--accent);
            color: #07221d;
            font-weight: 700;
            cursor: pointer;
            border: none;
        }}
        #action-status {{ margin-top: 10px; color: var(--muted); font-size: 13px; }}
        .links {{ margin-top: 16px; display: flex; gap: 14px; flex-wrap: wrap; }}
        @media (max-width: 760px) {{
            table {{ font-size: 12px; }}
            th, td {{ padding: 8px; }}
        }}
    </style>
</head>
<body>
    <div class='wrap'>
        <h1>K8s Cost Operator</h1>
        <p>Vue rapide des analyses générées par l'opérateur.</p>
        <div class='card'>
            <table>
                <thead>
                    <tr>
                        <th>Namespace</th>
                        <th>Status ConfigMap</th>
                        <th>Timestamp</th>
                        <th>Etat</th>
                        <th>Reco</th>
                        <th>Economies</th>
                        <th>Score</th>
                        <th>Rapport</th>
                    </tr>
                </thead>
                <tbody>{table_body}</tbody>
            </table>
        </div>
                <div class='actions'>
                        <h2>Déclencher un rapport</h2>
                        <div class='action-grid'>
                                <div class='action-card'>
                                        <h3>Rapport Global</h3>
                                        <p>Analyse tous les namespaces (hors exclusions par défaut).</p>
                                        <button id='btn-global'>Générer un rapport global</button>
                                </div>
                                <div class='action-card'>
                                        <h3>Rapport Namespace</h3>
                                        <p>Sélectionne un namespace précis et lance l'analyse dédiée.</p>
                                        <select id='namespace-select'></select>
                                        <button id='btn-ns'>Générer un rapport namespace</button>
                                </div>
                        </div>
                        <div id='action-status'>Prêt.</div>
                </div>
        <div class='links'>
            <a href='/healthz'>/healthz</a>
            <a href='/ready'>/ready</a>
            <a href='/api/reports'>/api/reports</a>
                        <a href='/api/namespaces'>/api/namespaces</a>
        </div>
    </div>
        <script>
            const statusEl = document.getElementById('action-status');
            const nsSelect = document.getElementById('namespace-select');

            const setStatus = (msg) => {{ statusEl.textContent = msg; }};

            async function loadNamespaces() {{
                try {{
                    const res = await fetch('/api/namespaces');
                    if (!res.ok) throw new Error('Erreur API namespaces');
                    const data = await res.json();
                    nsSelect.innerHTML = '';
                    (data.namespaces || []).forEach(ns => {{
                        const opt = document.createElement('option');
                        opt.value = ns;
                        opt.textContent = ns;
                        nsSelect.appendChild(opt);
                    }});
                    setStatus('Namespaces chargés.');
                }} catch (e) {{
                    setStatus('Impossible de charger les namespaces.');
                }}
            }}

            async function generate(scope, namespace='') {{
                setStatus('Génération en cours...');
                try {{
                    const res = await fetch('/api/reports/generate', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify({{ scope, namespace }})
                    }});
                    const data = await res.json();
                    if (!res.ok) {{
                        setStatus(`Erreur: ${{data.error || 'échec génération'}}`);
                        return;
                    }}
                    setStatus(`Rapport lancé: ${{data.name}} (${{data.namespace}})`);
                    setTimeout(() => window.location.reload(), 2500);
                }} catch (e) {{
                    setStatus('Erreur réseau lors de la génération.');
                }}
            }}

            document.getElementById('btn-global').addEventListener('click', () => generate('cluster'));
            document.getElementById('btn-ns').addEventListener('click', () => generate('namespace', nsSelect.value));

            loadNamespaces();
        </script>
</body>
</html>
"""


class FrontendHandler(BaseHTTPRequestHandler):
    def _send(self, body: str, status: int = 200, content_type: str = "text/html; charset=utf-8"):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        logger.debug("frontend: " + fmt, *args)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._send(_render_frontend_html())

        if path == "/healthz":
            return self._send("ok", content_type="text/plain; charset=utf-8")

        if path == "/ready":
            return self._send("ready", content_type="text/plain; charset=utf-8")

        if path == "/api/reports":
            data = json.dumps(_read_latest_report_statuses(limit=200), ensure_ascii=True, indent=2)
            return self._send(data, content_type="application/json; charset=utf-8")

        if path == "/api/namespaces":
            data = json.dumps({"namespaces": _list_namespaces()}, ensure_ascii=True, indent=2)
            return self._send(data, content_type="application/json; charset=utf-8")

        if path.startswith("/report/"):
            parts = [p for p in path.split("/") if p]
            if len(parts) != 3:
                return self._send("invalid report path", status=400, content_type="text/plain; charset=utf-8")

            namespace = parts[1]
            configmap_name = parts[2]
            try:
                report_cm = v1.read_namespaced_config_map(configmap_name, namespace)
                html = (report_cm.data or {}).get("report.html")
                if not html:
                    return self._send("report not found in configmap", status=404, content_type="text/plain; charset=utf-8")
                return self._send(html)
            except ApiException as exc:
                if exc.status == 404:
                    return self._send("report configmap not found", status=404, content_type="text/plain; charset=utf-8")
                logger.error(f"Erreur lecture rapport {namespace}/{configmap_name}: {exc}")
                return self._send("internal error", status=500, content_type="text/plain; charset=utf-8")

        return self._send("not found", status=404, content_type="text/plain; charset=utf-8")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path != "/api/reports/generate":
            return self._send("not found", status=404, content_type="text/plain; charset=utf-8")

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            payload = json.loads(raw)

            scope = payload.get("scope", "cluster")
            namespace = payload.get("namespace")

            if scope not in ("cluster", "namespace"):
                return self._send(
                    json.dumps({"error": "scope invalide"}),
                    status=400,
                    content_type="application/json; charset=utf-8",
                )

            if scope == "namespace" and not namespace:
                return self._send(
                    json.dumps({"error": "namespace requis"}),
                    status=400,
                    content_type="application/json; charset=utf-8",
                )

            report = _create_manual_costreport(scope=scope, target_namespace=namespace)
            return self._send(
                json.dumps(report, ensure_ascii=True),
                status=201,
                content_type="application/json; charset=utf-8",
            )
        except ApiException as exc:
            logger.error(f"Erreur API K8s génération rapport: {exc}")
            return self._send(
                json.dumps({"error": "erreur Kubernetes API"}),
                status=500,
                content_type="application/json; charset=utf-8",
            )
        except Exception as exc:
            logger.error(f"Erreur génération rapport: {exc}")
            return self._send(
                json.dumps({"error": str(exc)}),
                status=500,
                content_type="application/json; charset=utf-8",
            )


def _start_frontend_server():
        """Démarre le serveur HTTP embarqué (health probes + UI)."""
        server = HTTPServer((HTTP_HOST, HTTP_PORT), FrontendHandler)
        logger.info(f"Frontend HTTP démarré sur {HTTP_HOST}:{HTTP_PORT}")
        server.serve_forever()


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
        exclude_namespaces: List[str] = list(spec.get("excludeNamespaces", []))

        # Exclut par défaut le namespace de l'opérateur pour éviter l'auto-analyse bruitée.
        operator_namespace = os.getenv("POD_NAMESPACE", "cost-operator-system")
        if scope == "cluster" and operator_namespace not in exclude_namespaces:
            exclude_namespaces.append(operator_namespace)
        logger.info(f"Namespaces exclus de l'analyse: {exclude_namespaces}")
        
        # Détermine le scope d'analyse
        analysis_namespace = namespace if scope == "namespace" else None
        
        # Collecte les métriques
        logger.info("Collecte des métriques...")
        metrics_collector = MetricsCollector(prometheus_url=prometheus_url)
        
        # Analyse
        logger.info("Analyse des optimisations...")
        analyzer = CostAnalyzer(metrics_collector)
        recommendations = analyzer.analyze(
            namespace=analysis_namespace,
            exclude_namespaces=exclude_namespaces,
        )
        
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
    frontend_thread = threading.Thread(target=_start_frontend_server, daemon=True)
    frontend_thread.start()
    kopf.run()
