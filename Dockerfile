FROM python:3.11-slim

WORKDIR /app

# Installe les dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copie les requirements et installe les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le code de l'opérateur
COPY main.py .
COPY metrics.py .
COPY analyzer.py .
COPY report.py .

# Crée l'utilisateur non-root
RUN useradd -m -u 1000 operator && \
    chown -R operator:operator /app

USER operator

# Health check endpoint (simple)
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/healthz || exit 1

# Exécute l'opérateur
CMD ["python", "-u", "main.py"]
