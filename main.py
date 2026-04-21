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
from html import escape
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
REPORT_FOLDER_ANNOTATION = "cost.k8s.io/folder"


def _normalize_folder(folder: Optional[str]) -> str:
    """Normalise un nom de dossier pour stockage et affichage."""
    return (folder or "").strip()


def _display_folder(folder: str) -> str:
    """Retourne un libellé lisible pour le front."""
    return folder if folder else "Sans dossier"


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


def _create_manual_costreport(
        scope: str,
        target_namespace: Optional[str] = None,
        folder: Optional[str] = None,
) -> Dict[str, str]:
    """Crée un CostReport manuel qui déclenchera une analyse immédiate via les handlers Kopf."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    cluster_name = os.getenv("CLUSTER_NAME", "kubernetes")
    prometheus_url = os.getenv("PROMETHEUS_URL", "").strip()
    folder_name = _normalize_folder(folder)

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
        "folder": folder_name,
    }
    if prometheus_url:
        spec["prometheusUrl"] = prometheus_url

    body = {
        "apiVersion": "cost.k8s.io/v1",
        "kind": "CostReport",
        "metadata": {
            "name": report_name,
            "namespace": report_namespace,
            "annotations": {
                REPORT_FOLDER_ANNOTATION: folder_name,
            },
        },
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
        "folder": folder_name,
        "status_configmap": f"cost-report-status-{report_name}",
    }


def _read_report_status(namespace: str, report_name: str) -> Optional[Dict[str, str]]:
    """Lit le ConfigMap de statut associé à un CostReport."""
    status_name = f"cost-report-status-{report_name}"

    try:
        status_cm = v1.read_namespaced_config_map(status_name, namespace)
    except ApiException as exc:
        if exc.status == 404:
            return None
        raise

    data = status_cm.data or {}
    annotations = status_cm.metadata.annotations or {}
    folder = _normalize_folder(
        data.get("folder") or annotations.get(REPORT_FOLDER_ANNOTATION, "")
    )

    return {
        "name": status_cm.metadata.name,
        "namespace": namespace,
        "report_name": data.get("report_name", report_name),
        "report": data.get("configmap_name", ""),
        "timestamp": data.get("timestamp", ""),
        "recommendations": data.get("recommendations_count", ""),
        "savings": data.get("total_savings", ""),
        "score": data.get("optimization_score", ""),
        "status": data.get("status", "unknown"),
        "folder": folder,
    }


def _update_report_folder(namespace: str, report_name: str, folder: str):
    """Met à jour le dossier du CostReport et des artefacts associés."""
    folder_name = _normalize_folder(folder)
    status_name = f"cost-report-status-{report_name}"

    try:
        status_cm = v1.read_namespaced_config_map(status_name, namespace)
    except ApiException as exc:
        if exc.status == 404:
            raise ValueError(f"rapport introuvable: {namespace}/{report_name}") from exc
        raise

    status_data = dict(status_cm.data or {})
    status_data.update({"report_name": report_name, "folder": folder_name})
    status_annotations = dict(status_cm.metadata.annotations or {})
    if folder_name:
        status_annotations[REPORT_FOLDER_ANNOTATION] = folder_name
    else:
        status_annotations.pop(REPORT_FOLDER_ANNOTATION, None)

    v1.patch_namespaced_config_map(
        status_name,
        namespace,
        {
            "metadata": {"annotations": status_annotations},
            "data": status_data,
        },
    )

    report_cm_name = status_data.get("configmap_name", "")
    if report_cm_name:
        try:
            report_cm = v1.read_namespaced_config_map(report_cm_name, namespace)
            report_data = dict(report_cm.data or {})
            report_annotations = dict(report_cm.metadata.annotations or {})
            if folder_name:
                report_annotations[REPORT_FOLDER_ANNOTATION] = folder_name
            else:
                report_annotations.pop(REPORT_FOLDER_ANNOTATION, None)
            report_data["folder"] = folder_name
            v1.patch_namespaced_config_map(
                report_cm_name,
                namespace,
                {
                    "metadata": {"annotations": report_annotations},
                    "data": report_data,
                },
            )
        except ApiException as exc:
            if exc.status != 404:
                raise

    try:
        costreport = custom_api.get_namespaced_custom_object(
            "cost.k8s.io",
            "v1",
            namespace,
            "costreports",
            report_name,
        )
    except ApiException as exc:
        if exc.status == 404:
            return
        raise

    metadata = costreport.get("metadata", {})
    annotations = dict(metadata.get("annotations") or {})
    if folder_name:
        annotations[REPORT_FOLDER_ANNOTATION] = folder_name
    else:
        annotations.pop(REPORT_FOLDER_ANNOTATION, None)

    spec = dict(costreport.get("spec") or {})
    if folder_name:
        spec["folder"] = folder_name
    else:
        spec.pop("folder", None)

    metadata["annotations"] = annotations
    costreport["metadata"] = metadata
    costreport["spec"] = spec

    custom_api.patch_namespaced_custom_object(
        "cost.k8s.io",
        "v1",
        namespace,
        "costreports",
        report_name,
        costreport,
    )


def _delete_report(namespace: str, report_name: str):
    """Supprime le CostReport et ses ConfigMaps associés."""
    deleted = {
        "namespace": namespace,
        "report_name": report_name,
        "status_configmap": f"cost-report-status-{report_name}",
        "report_configmap": "",
        "costreport": False,
    }

    status = _read_report_status(namespace, report_name)
    if status:
        deleted["report_configmap"] = status.get("report", "")

    try:
        custom_api.delete_namespaced_custom_object(
            "cost.k8s.io",
            "v1",
            namespace,
            "costreports",
            report_name,
        )
        deleted["costreport"] = True
    except ApiException as exc:
        if exc.status != 404:
            raise

    if deleted["report_configmap"]:
        try:
            v1.delete_namespaced_config_map(deleted["report_configmap"], namespace)
        except ApiException as exc:
            if exc.status != 404:
                raise

    try:
        v1.delete_namespaced_config_map(deleted["status_configmap"], namespace)
    except ApiException as exc:
        if exc.status != 404:
            raise

    return deleted


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
                    "report_name": data.get("report_name", item.metadata.name.removeprefix("cost-report-status-")),
                                "report": data.get("configmap_name", ""),
                                "timestamp": data.get("timestamp", ""),
                                "recommendations": data.get("recommendations_count", ""),
                                "savings": data.get("total_savings", ""),
                                "score": data.get("optimization_score", ""),
                                "status": data.get("status", "unknown"),
                    "folder": _normalize_folder(
                        data.get("folder") or (item.metadata.annotations or {}).get(REPORT_FOLDER_ANNOTATION, "")
                    ),
                        }
                )

        reports.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return reports[:limit]


def _render_frontend_html() -> str:
        """Construit un front HTML léger pour visualiser les analyses récentes."""
        reports = _read_latest_report_statuses(limit=100)
        rows = []
        folders = []
        seen_folders = set()

        for report in reports:
                folder_label = _display_folder(report["folder"])
                if folder_label not in seen_folders:
                        seen_folders.add(folder_label)
                        folders.append(folder_label)

                view_link = "-"
                if report["report"]:
                        view_link = (
                                f"<a href='/report/{report['namespace']}/{report['report']}'>"
                                "ouvrir le rapport"
                                "</a>"
                        )

                rows.append(
                        f"<tr data-folder='{escape(folder_label)}'>"
                        f"<td>{escape(folder_label)}</td>"
                        f"<td>{escape(report['namespace'])}</td>"
                        f"<td>{escape(report['report_name'])}</td>"
                        f"<td>{escape(report['timestamp'] or '-')}</td>"
                        f"<td>{escape(report['status'])}</td>"
                        f"<td>{escape(report['recommendations'] or '-')}</td>"
                        f"<td>{escape(report['savings'] or '-')}</td>"
                        f"<td>{escape(report['score'] or '-')}</td>"
                        f"<td>{view_link}</td>"
                        "<td>"
                        "<div class='row-tools'>"
                        f"<input class='folder-field' type='text' value='{escape(report['folder'])}' placeholder='Sans dossier' />"
                        f"<button class='secondary folder-save' data-namespace='{escape(report['namespace'])}' data-report='{escape(report['report_name'])}'>Déplacer</button>"
                        f"<button class='danger report-delete' data-namespace='{escape(report['namespace'])}' data-report='{escape(report['report_name'])}'>Supprimer</button>"
                        "</div>"
                        "</td>"
                        "</tr>"
                )

        folder_options = "".join(
                f"<option value='{escape(folder)}'>{escape(folder)}</option>"
                for folder in folders
        )

        table_body = "".join(rows) or (
                "<tr><td colspan='10'>Aucun rapport trouvé pour le moment.</td></tr>"
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
        .wrap {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
        h1 {{ margin-bottom: 8px; }}
        p {{ color: var(--muted); margin-top: 0; }}
        .card {{
            background: color-mix(in oklab, var(--card), black 8%);
            border: 1px solid var(--border);
            border-radius: 14px;
            overflow: hidden;
        }}
        .filters {{
            display: flex;
            gap: 12px;
            align-items: center;
            margin: 18px 0 14px;
            flex-wrap: wrap;
        }}
        .filters label {{ color: var(--muted); font-size: 13px; }}
        .filters select {{ width: auto; min-width: 220px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }}
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
        button, select, input {{
            width: 100%;
            padding: 10px;
            border-radius: 10px;
            border: 1px solid var(--border);
            background: #0f1b2e;
            color: var(--text);
            box-sizing: border-box;
        }}
        button {{
            margin-top: 8px;
            background: var(--accent);
            color: #07221d;
            font-weight: 700;
            cursor: pointer;
            border: none;
        }}
        button.secondary {{ background: #21324d; color: var(--text); }}
        button.danger {{ background: #8f2f2f; color: #fff; }}
        .row-tools {{ display: grid; gap: 8px; min-width: 260px; }}
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
        <div class='filters'>
            <label for='folder-filter'>Filtrer par dossier</label>
            <select id='folder-filter'>
                <option value='__all__'>Tous les dossiers</option>
                {folder_options}
            </select>
        </div>
        <div class='card'>
            <table>
                <thead>
                    <tr>
                        <th>Dossier</th>
                        <th>Namespace</th>
                        <th>Rapport</th>
                        <th>Timestamp</th>
                        <th>Etat</th>
                        <th>Reco</th>
                        <th>Economies</th>
                        <th>Score</th>
                        <th>Rapport</th>
                        <th>Actions</th>
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
                    <input id='folder-input-global' type='text' placeholder='Dossier du rapport' />
                    <button id='btn-global'>Générer un rapport global</button>
                </div>
                <div class='action-card'>
                    <h3>Rapport Namespace</h3>
                    <p>Sélectionne un namespace précis et lance l'analyse dédiée.</p>
                    <select id='namespace-select'></select>
                    <input id='folder-input-namespace' type='text' placeholder='Dossier du rapport' />
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
            <a href='/api/folders'>/api/folders</a>
        </div>
    </div>
    <script>
        const statusEl = document.getElementById('action-status');
        const nsSelect = document.getElementById('namespace-select');
        const folderFilter = document.getElementById('folder-filter');
        const folderInputGlobal = document.getElementById('folder-input-global');
        const folderInputNamespace = document.getElementById('folder-input-namespace');

        const setStatus = (msg) => {{ statusEl.textContent = msg; }};

        const normalizeFolder = (value) => (value || '').trim();
        const folderLabel = (value) => value ? value : 'Sans dossier';

        function applyFolderFilter() {{
            const selected = folderFilter.value;
            document.querySelectorAll('tbody tr[data-folder]').forEach((row) => {{
                const folder = row.getAttribute('data-folder') || '';
                row.style.display = selected === '__all__' || selected === folder ? '' : 'none';
            }});
        }}

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
                const folder = scope === 'namespace' ? normalizeFolder(folderInputNamespace.value) : normalizeFolder(folderInputGlobal.value);
                const res = await fetch('/api/reports/generate', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ scope, namespace, folder }})
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

        async function patchFolder(namespace, reportName, folder) {{
            const res = await fetch('/api/reports/folder', {{
                method: 'PATCH',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ namespace, report_name: reportName, folder }})
            }});
            const data = await res.json();
            if (!res.ok) {{
                throw new Error(data.error || 'mise à jour du dossier impossible');
            }}
            return data;
        }}

        async function deleteReport(namespace, reportName) {{
            const res = await fetch('/api/reports', {{
                method: 'DELETE',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ namespace, report_name: reportName }})
            }});
            const data = await res.json();
            if (!res.ok) {{
                throw new Error(data.error || 'suppression impossible');
            }}
            return data;
        }}

        document.querySelectorAll('.folder-save').forEach((button) => {{
            button.addEventListener('click', async () => {{
                const namespace = button.dataset.namespace;
                const reportName = button.dataset.report;
                const field = button.closest('tr').querySelector('.folder-field');
                const folder = normalizeFolder(field ? field.value : '');
                setStatus(`Déplacement de ${{reportName}} vers ${{folderLabel(folder)}}...`);
                try {{
                    await patchFolder(namespace, reportName, folder);
                    setStatus(`Dossier mis à jour pour ${{reportName}}.`);
                    setTimeout(() => window.location.reload(), 1000);
                }} catch (error) {{
                    setStatus(`Erreur: ${{error.message}}`);
                }}
            }});
        }});

        document.querySelectorAll('.report-delete').forEach((button) => {{
            button.addEventListener('click', async () => {{
                const namespace = button.dataset.namespace;
                const reportName = button.dataset.report;
                if (!window.confirm(`Supprimer le rapport ${{reportName}} ?`)) {{
                    return;
                }}
                setStatus(`Suppression de ${{reportName}}...`);
                try {{
                    await deleteReport(namespace, reportName);
                    setStatus(`Rapport supprimé: ${{reportName}}.`);
                    setTimeout(() => window.location.reload(), 1000);
                }} catch (error) {{
                    setStatus(`Erreur: ${{error.message}}`);
                }}
            }});
        }});

        document.getElementById('btn-global').addEventListener('click', () => generate('cluster'));
        document.getElementById('btn-ns').addEventListener('click', () => generate('namespace', nsSelect.value));
        folderFilter.addEventListener('change', applyFolderFilter);

        loadNamespaces();
        applyFolderFilter();
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

        if path == "/api/folders":
            folders = sorted({
                _display_folder(report["folder"])
                for report in _read_latest_report_statuses(limit=200)
            })
            data = json.dumps({"folders": folders}, ensure_ascii=True, indent=2)
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
            folder = payload.get("folder", "")

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

            report = _create_manual_costreport(scope=scope, target_namespace=namespace, folder=folder)
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

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path != "/api/reports/folder":
            return self._send("not found", status=404, content_type="text/plain; charset=utf-8")

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            payload = json.loads(raw)

            namespace = payload.get("namespace")
            report_name = payload.get("report_name")
            folder = payload.get("folder", "")

            if not namespace or not report_name:
                return self._send(
                    json.dumps({"error": "namespace et report_name requis"}),
                    status=400,
                    content_type="application/json; charset=utf-8",
                )

            _update_report_folder(namespace, report_name, folder)
            return self._send(
                json.dumps(
                    {
                        "status": "folder_updated",
                        "namespace": namespace,
                        "report_name": report_name,
                        "folder": _normalize_folder(folder),
                    },
                    ensure_ascii=True,
                ),
                content_type="application/json; charset=utf-8",
            )
        except ApiException as exc:
            logger.error(f"Erreur API K8s mise à jour dossier rapport: {exc}")
            return self._send(
                json.dumps({"error": "erreur Kubernetes API"}),
                status=500,
                content_type="application/json; charset=utf-8",
            )
        except Exception as exc:
            logger.error(f"Erreur mise à jour dossier rapport: {exc}")
            return self._send(
                json.dumps({"error": str(exc)}),
                status=500,
                content_type="application/json; charset=utf-8",
            )

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path != "/api/reports":
            return self._send("not found", status=404, content_type="text/plain; charset=utf-8")

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            payload = json.loads(raw)

            namespace = payload.get("namespace")
            report_name = payload.get("report_name")

            if not namespace or not report_name:
                return self._send(
                    json.dumps({"error": "namespace et report_name requis"}),
                    status=400,
                    content_type="application/json; charset=utf-8",
                )

            deleted = _delete_report(namespace, report_name)
            return self._send(
                json.dumps({"status": "deleted", **deleted}, ensure_ascii=True),
                content_type="application/json; charset=utf-8",
            )
        except ApiException as exc:
            logger.error(f"Erreur API K8s suppression rapport: {exc}")
            return self._send(
                json.dumps({"error": "erreur Kubernetes API"}),
                status=500,
                content_type="application/json; charset=utf-8",
            )
        except Exception as exc:
            logger.error(f"Erreur suppression rapport: {exc}")
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
    annotations = kwargs.get("annotations") or {}
    if not spec.get("folder"):
        folder = _normalize_folder(annotations.get(REPORT_FOLDER_ANNOTATION, ""))
        if folder:
            spec["folder"] = folder
    
    # Exécute l'analyse immédiatement
    _run_analysis(spec, name, namespace)
    
    return {"status": "initial_report_generated"}


@kopf.on.update("cost.k8s.io", "v1", "costreports")
def update_costreport(spec, name, namespace, **kwargs):
    """
    Met à jour le rapport quand une CRD CostReport est modifiée
    """
    logger.info(f"CostReport mis à jour: {namespace}/{name}")
    annotations = kwargs.get("annotations") or {}
    if not spec.get("folder"):
        folder = _normalize_folder(annotations.get(REPORT_FOLDER_ANNOTATION, ""))
        if folder:
            spec["folder"] = folder
    
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
    annotations = kwargs.get("annotations") or {}
    if not spec.get("folder"):
        folder = _normalize_folder(annotations.get(REPORT_FOLDER_ANNOTATION, ""))
        if folder:
            spec["folder"] = folder
    
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
        folder = _normalize_folder(spec.get("folder", ""))
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
                "status": "completed",
                "report_name": name,
                "folder": folder,
            }, folder=folder)
        
        else:  # output_type == "configmap"
            html_report = report_generator.generate_html(cluster_name)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            configmap_name = f"cost-report-{name}-{timestamp}"
            
            _save_report_to_configmap(namespace, configmap_name, html_report, folder=folder)
            logger.info(f"Rapport sauvegardé en ConfigMap: {configmap_name}")
            
            # Crée un ConfigMap de statut
            _create_report_status_configmap(name, namespace, {
                "configmap_name": configmap_name,
                "timestamp": timestamp,
                "recommendations_count": len(recommendations),
                "total_savings": f"${analyzer.calculate_total_savings():.2f}",
                "optimization_score": f"{analyzer.calculate_optimization_score():.1f}%",
                "status": "completed",
                "report_name": name,
                "folder": folder,
            }, folder=folder)
        
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


def _save_report_to_configmap(namespace: str, configmap_name: str, html_content: str, folder: str = ""):
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
                "annotations": {
                    REPORT_FOLDER_ANNOTATION: folder,
                } if folder else {},
                "labels": {
                    "app": "cost-optimization-operator",
                    "type": "cost-report"
                }
            },
            "data": {
                "folder": folder,
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


def _create_report_status_configmap(report_name: str, namespace: str, status_data: Dict, folder: str = ""):
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
                "annotations": {
                    REPORT_FOLDER_ANNOTATION: folder,
                } if folder else {},
                "labels": {
                    "app": "cost-optimization-operator",
                    "type": "cost-report-status"
                }
            },
            "data": {
                **{key: str(value) for key, value in status_data.items()},
                "report_name": report_name,
                "folder": folder,
            }
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
