"""
Module de génération du rapport HTML
"""

import logging
from typing import List, Dict
from datetime import datetime
from jinja2 import Template
from analyzer import Recommendation, CostAnalyzer

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Génère des rapports HTML d'optimisation des coûts"""
    
    HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rapport d'Optimisation des Coûts Kubernetes</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
            overflow: hidden;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.1em;
            opacity: 0.9;
        }
        
        .content {
            padding: 40px;
        }
        
        .metadata {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 6px;
        }
        
        .metadata-item {
            border-left: 4px solid #667eea;
            padding-left: 15px;
        }
        
        .metadata-item label {
            display: block;
            font-weight: 600;
            color: #667eea;
            font-size: 0.9em;
            text-transform: uppercase;
            margin-bottom: 5px;
        }
        
        .metadata-item value {
            display: block;
            font-size: 1.2em;
            color: #333;
        }
        
        .summary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 6px;
            margin-bottom: 30px;
        }
        
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }
        
        .summary-card {
            background: rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 6px;
            border-left: 4px solid rgba(255, 255, 255, 0.3);
        }
        
        .summary-card h3 {
            font-size: 0.9em;
            text-transform: uppercase;
            opacity: 0.8;
            margin-bottom: 10px;
        }
        
        .summary-card .value {
            font-size: 2em;
            font-weight: bold;
        }
        
        .score-circle {
            display: inline-block;
            width: 100px;
            height: 100px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.2);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 2.5em;
            font-weight: bold;
            border: 3px solid white;
        }
        
        .recommendations {
            margin-top: 30px;
        }
        
        .recommendations h2 {
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #667eea;
        }
        
        .priority-tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            border-bottom: 1px solid #ddd;
        }
        
        .priority-tab {
            padding: 12px 20px;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 1em;
            font-weight: 600;
            color: #999;
            border-bottom: 3px solid transparent;
            transition: all 0.3s;
        }
        
        .priority-tab.active {
            color: #667eea;
            border-bottom-color: #667eea;
        }
        
        .priority-tab:hover {
            color: #667eea;
        }
        
        .recommendation-card {
            background: #f8f9fa;
            border-left: 4px solid #667eea;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 4px;
            transition: all 0.3s;
        }
        
        .recommendation-card:hover {
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.1);
        }
        
        .recommendation-card.priority-high {
            border-left-color: #e74c3c;
            background: #fadbd8;
        }
        
        .recommendation-card.priority-medium {
            border-left-color: #f39c12;
            background: #fdebd0;
        }
        
        .recommendation-card.priority-low {
            border-left-color: #27ae60;
            background: #d5f4e6;
        }
        
        .recommendation-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        
        .recommendation-title {
            font-size: 1.2em;
            font-weight: 600;
            color: #333;
        }
        
        .recommendation-type {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
            background: rgba(102, 126, 234, 0.2);
            color: #667eea;
        }
        
        .recommendation-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
            padding: 15px 0;
            border-top: 1px solid rgba(0, 0, 0, 0.1);
            border-bottom: 1px solid rgba(0, 0, 0, 0.1);
        }
        
        .detail-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .detail-item label {
            font-weight: 600;
            color: #666;
            margin-right: 10px;
        }
        
        .detail-item .current {
            color: #e74c3c;
        }
        
        .detail-item .arrow {
            color: #667eea;
            margin: 0 5px;
        }
        
        .detail-item .recommended {
            color: #27ae60;
            font-weight: 600;
        }
        
        .reasoning {
            color: #666;
            font-size: 0.95em;
            font-style: italic;
            padding: 10px;
            background: rgba(0, 0, 0, 0.02);
            border-radius: 4px;
            margin-top: 10px;
        }
        
        .savings {
            display: inline-block;
            padding: 8px 16px;
            background: #27ae60;
            color: white;
            border-radius: 20px;
            font-weight: 600;
            margin-top: 10px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: white;
            border-radius: 6px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        
        th {
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }
        
        td {
            padding: 12px 15px;
            border-bottom: 1px solid #eee;
        }
        
        tr:hover {
            background: #f8f9fa;
        }
        
        .namespace-section {
            margin-bottom: 40px;
            padding-bottom: 20px;
            border-bottom: 2px solid #eee;
        }
        
        .namespace-section h3 {
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.3em;
        }
        
        .footer {
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #999;
            border-top: 1px solid #ddd;
        }
        
        .badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 600;
        }
        
        .badge-high {
            background: #e74c3c;
            color: white;
        }
        
        .badge-medium {
            background: #f39c12;
            color: white;
        }
        
        .badge-low {
            background: #27ae60;
            color: white;
        }
        
        @media print {
            body {
                background: white;
            }
            .container {
                box-shadow: none;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Rapport d'Optimisation des Coûts</h1>
            <p>Kubernetes Cost Optimization Report</p>
        </div>
        
        <div class="content">
            <!-- Métadonnées -->
            <div class="metadata">
                <div class="metadata-item">
                    <label>Date du rapport</label>
                    <value>{{ report_date }}</value>
                </div>
                <div class="metadata-item">
                    <label>Cluster</label>
                    <value>{{ cluster_name }}</value>
                </div>
                <div class="metadata-item">
                    <label>Namespaces analysés</label>
                    <value>{{ namespaces_count }}</value>
                </div>
                <div class="metadata-item">
                    <label>Pods analysés</label>
                    <value>{{ pods_count }}</value>
                </div>
            </div>
            
            <!-- Résumé -->
            <div class="summary">
                <div class="summary-grid">
                    <div class="summary-card">
                        <h3>💰 Économies potentielles</h3>
                        <div class="value">${{ total_savings | round(2) }}/mois</div>
                    </div>
                    <div class="summary-card">
                        <h3>🎯 Score d'optimisation</h3>
                        <div class="score-circle">{{ optimization_score | round(0) }}%</div>
                    </div>
                    <div class="summary-card">
                        <h3>⚠️ Recommandations</h3>
                        <div class="value">{{ recommendations_count }}</div>
                    </div>
                    <div class="summary-card">
                        <h3>🔴 Haute priorité</h3>
                        <div class="value">{{ high_priority_count }}</div>
                    </div>
                </div>
            </div>
            
            <!-- Recommandations par priorité -->
            {% if recommendations %}
            <div class="recommendations">
                <h2>Recommandations d'Optimisation</h2>
                
                {% for priority in ['high', 'medium', 'low'] %}
                    {% if recommendations_by_priority[priority] %}
                    <div class="priority-section">
                        <h3 style="margin-top: 30px; margin-bottom: 15px;">
                            {% if priority == 'high' %}🔴 Haute priorité{% elif priority == 'medium' %}🟡 Priorité normale{% else %}🟢 Basse priorité{% endif %}
                        </h3>
                        
                        {% for rec in recommendations_by_priority[priority] %}
                        <div class="recommendation-card priority-{{ priority }}">
                            <div class="recommendation-header">
                                <div>
                                    <div class="recommendation-title">
                                        {{ rec.workload_name }} <span style="color: #999;">[{{ rec.namespace }}]</span>
                                    </div>
                                </div>
                                <div>
                                    <span class="recommendation-type">{{ rec.optimization_type | replace('_', ' ') | title }}</span>
                                </div>
                            </div>
                            
                            <div class="recommendation-details">
                                {% if rec.optimization_type in ['cpu_reduction', 'remove'] %}
                                <div class="detail-item">
                                    <label>CPU request:</label>
                                    <span class="current">{{ rec.current_cpu_request | round(3) }} cores</span>
                                    <span class="arrow">→</span>
                                    <span class="recommended">{{ rec.recommended_cpu_request | round(3) }} cores</span>
                                </div>
                                {% endif %}
                                
                                {% if rec.optimization_type in ['memory_reduction', 'remove'] %}
                                <div class="detail-item">
                                    <label>Memory request:</label>
                                    <span class="current">{{ rec.current_memory_request | round(0) }} MiB</span>
                                    <span class="arrow">→</span>
                                    <span class="recommended">{{ rec.recommended_memory_request | round(0) }} MiB</span>
                                </div>
                                {% endif %}
                                
                                {% if rec.optimization_type == 'scale_down' %}
                                <div class="detail-item">
                                    <label>Replicas:</label>
                                    <span class="current">{{ rec.current_replicas }}</span>
                                    <span class="arrow">→</span>
                                    <span class="recommended">{{ rec.recommended_replicas }}</span>
                                </div>
                                {% endif %}
                            </div>
                            
                            <div class="reasoning">
                                📋 {{ rec.reasoning }}
                            </div>
                            
                            <span class="savings">💡 Économies: {{ rec.estimated_savings_percent | round(1) }}%</span>
                        </div>
                        {% endfor %}
                    </div>
                    {% endif %}
                {% endfor %}
            </div>
            {% endif %}
            
            <!-- Tableau récapitulatif -->
            {% if recommendations %}
            <div class="recommendations">
                <h2 style="margin-top: 40px;">Tableau Récapitulatif</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Workload</th>
                            <th>Namespace</th>
                            <th>Type</th>
                            <th>Priorité</th>
                            <th>Économies %</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for rec in recommendations %}
                        <tr>
                            <td><strong>{{ rec.workload_name }}</strong></td>
                            <td>{{ rec.namespace }}</td>
                            <td>{{ rec.optimization_type | replace('_', ' ') | title }}</td>
                            <td>
                                <span class="badge badge-{{ rec.priority }}">
                                    {{ rec.priority | upper }}
                                </span>
                            </td>
                            <td>{{ rec.estimated_savings_percent | round(1) }}%</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% endif %}
            
            <!-- Recommandations par Namespace -->
            {% if namespace_summaries %}
            <div class="recommendations">
                <h2 style="margin-top: 40px;">Résumé par Namespace</h2>
                {% for ns_summary in namespace_summaries %}
                <div class="namespace-section">
                    <h3>{{ ns_summary.namespace }}</h3>
                    <div class="summary-grid">
                        <div class="summary-card" style="background: white; border: 1px solid #ddd;">
                            <h3>Pods</h3>
                            <div class="value">{{ ns_summary.pods_count }}</div>
                        </div>
                        <div class="summary-card" style="background: white; border: 1px solid #ddd;">
                            <h3>Recommandations</h3>
                            <div class="value">{{ ns_summary.recommendations_count }}</div>
                        </div>
                        <div class="summary-card" style="background: white; border: 1px solid #ddd;">
                            <h3>Économies potentielles</h3>
                            <div class="value">${{ ns_summary.potential_savings | round(2) }}/mois</div>
                        </div>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endif %}
        </div>
        
        <div class="footer">
            <p>Rapport généré automatiquement par K8s Cost Optimization Operator</p>
            <p style="margin-top: 10px; font-size: 0.9em;">Les économies estimées sont basées sur des analyses heuristiques. Une validation manuelle est recommandée avant d'appliquer les changements.</p>
        </div>
    </div>
</body>
</html>
"""
    
    def __init__(self, analyzer: CostAnalyzer):
        """
        Initialise le générateur de rapport
        
        Args:
            analyzer: Instance de CostAnalyzer avec les recommandations
        """
        self.analyzer = analyzer
        self.template = Template(self.HTML_TEMPLATE)
    
    def generate_html(
        self,
        cluster_name: str = "kubernetes-cluster",
        include_namespace_summary: bool = True
    ) -> str:
        """
        Génère le rapport HTML complet
        
        Args:
            cluster_name: Nom du cluster Kubernetes
            include_namespace_summary: Inclure un résumé par namespace
        
        Returns:
            str: HTML du rapport
        """
        recommendations = self.analyzer.recommendations
        recommendations_by_priority = self.analyzer.get_recommendations_by_priority()
        recommendations_by_namespace = self.analyzer.get_recommendations_by_namespace()
        
        # Calcule les statistiques
        namespace_summaries = []
        if include_namespace_summary:
            for ns, recs in recommendations_by_namespace.items():
                ns_summary = {
                    'namespace': ns,
                    'recommendations_count': len(recs),
                    'pods_count': len(set(f"{r.namespace}/{r.workload_name}" for r in recs)),
                    'potential_savings': sum(
                        r.estimated_savings_percent * (r.current_cpu_request * 10 +
                                                      r.current_memory_request / 1024)
                        for r in recs
                    )
                }
                namespace_summaries.append(ns_summary)
        
        context = {
            'report_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'cluster_name': cluster_name,
            'namespaces_count': len(recommendations_by_namespace),
            'pods_count': len(set(f"{r.namespace}/{r.workload_name}" for r in recommendations)),
            'recommendations_count': len(recommendations),
            'high_priority_count': len(recommendations_by_priority['high']),
            'total_savings': self.analyzer.calculate_total_savings(),
            'optimization_score': self.analyzer.calculate_optimization_score(),
            'recommendations': recommendations,
            'recommendations_by_priority': recommendations_by_priority,
            'namespace_summaries': namespace_summaries,
        }
        
        html = self.template.render(context)
        logger.info(f"Rapport HTML généré avec {len(recommendations)} recommandations")
        return html
    
    def save_to_file(self, filepath: str, cluster_name: str = "kubernetes-cluster"):
        """
        Sauvegarde le rapport en fichier HTML
        
        Args:
            filepath: Chemin du fichier (ex: /tmp/report-2024-01-01.html)
            cluster_name: Nom du cluster
        """
        html = self.generate_html(cluster_name)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"Rapport sauvegardé: {filepath}")
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde: {e}")
            raise
    
    def get_html_for_configmap(self, cluster_name: str = "kubernetes-cluster") -> str:
        """
        Génère le HTML optimisé pour ConfigMap Kubernetes
        
        Returns:
            str: HTML comprimé
        """
        html = self.generate_html(cluster_name)
        # Compress les espaces inutiles
        import re
        html = re.sub(r'\s+', ' ', html)
        return html
