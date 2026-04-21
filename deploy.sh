#!/bin/bash
# =============================================================================
# deploy.sh — déploiement complet sur Minikube
# Usage: ./deploy.sh <votre-dockerhub-username>
# =============================================================================
set -e

DOCKERHUB_USER=${1:-"massizelle"}

echo "============================================================"
echo " URLShort — Déploiement Minikube"
echo " Docker Hub user: $DOCKERHUB_USER"
echo "============================================================"

# ── 1. Build & push images ────────────────────────────────────────────
echo ""
echo "[1/6] Build et push des images Docker..."

# Shortener — construit depuis la racine avec Dockerfile.shortener
# (ce Dockerfile copie shortener-service/ + proto/ dans le même contexte)
docker build \
  -t "$DOCKERHUB_USER/shortener-service:latest" \
  -f Dockerfile.shortener \
  .

# Analytics — même principe avec Dockerfile.analytics
docker build \
  -t "$DOCKERHUB_USER/analytics-service:latest" \
  -f Dockerfile.analytics \
  .

# Frontend — avec les URLs de l'ingress Istio (urlshort.local)
docker build \
  --build-arg VITE_SHORTENER_URL=http://urlshort.local \
  --build-arg VITE_ANALYTICS_URL=http://urlshort.local \
  -t "$DOCKERHUB_USER/urlshort-frontend:latest" \
  frontend/

docker push "$DOCKERHUB_USER/shortener-service:latest"
docker push "$DOCKERHUB_USER/analytics-service:latest"
docker push "$DOCKERHUB_USER/urlshort-frontend:latest"

echo "✓ Images publiées sur Docker Hub"

# ── 2. Patch image names dans les yamls ──────────────────────────────
echo ""
echo "[2/6] Mise à jour des noms d'images dans les manifests..."

# Remplace le nom d'utilisateur Docker Hub actuel par celui passé en argument
sed -i "s|massizelle/|$DOCKERHUB_USER/|g" \
  k8s/shortener/shortener-deployment.yaml \
  k8s/shortener/frontend-deployment.yaml \
  k8s/analytics/analytics-deployment.yaml

echo "✓ Manifests mis à jour"

# ── 3. Namespace + Istio ──────────────────────────────────────────────
echo ""
echo "[3/6] Création du namespace + config Istio..."

kubectl apply -f k8s/istio/istio-config.yaml
sleep 2

echo "✓ Namespace 'urlshort' créé avec injection Istio"

# ── 4. RBAC ───────────────────────────────────────────────────────────
echo ""
echo "[4/6] Application des RBAC..."
kubectl apply -f k8s/rbac/rbac.yaml
echo "✓ RBAC appliqués"

# ── 5. Bases de données ───────────────────────────────────────────────
echo ""
echo "[5/6] Déploiement des bases PostgreSQL..."
kubectl apply -f k8s/postgres-shortener/postgres-shortener.yaml
kubectl apply -f k8s/postgres-analytics/postgres-analytics.yaml

echo "Attente que PostgreSQL soit prêt..."
kubectl wait --for=condition=ready pod \
  -l app=postgres-shortener \
  -n urlshort \
  --timeout=120s

kubectl wait --for=condition=ready pod \
  -l app=postgres-analytics \
  -n urlshort \
  --timeout=120s

echo "✓ PostgreSQL prêts"

# ── 6. Microservices + Frontend ───────────────────────────────────────
echo ""
echo "[6/6] Déploiement des microservices et du frontend..."
kubectl apply -f k8s/shortener/shortener-deployment.yaml
kubectl apply -f k8s/analytics/analytics-deployment.yaml
kubectl apply -f k8s/shortener/frontend-deployment.yaml

kubectl wait --for=condition=ready pod \
  -l app=shortener-service \
  -n urlshort \
  --timeout=120s

kubectl wait --for=condition=ready pod \
  -l app=analytics-service \
  -n urlshort \
  --timeout=120s

echo ""
echo "============================================================"
echo " ✅ Déploiement terminé !"
echo "============================================================"
echo ""
MINIKUBE_IP=$(minikube ip)
echo "Ajoutez cette ligne à C:\\Windows\\System32\\drivers\\etc\\hosts :"
echo "  $MINIKUBE_IP  urlshort.local"
echo ""
echo "Puis ouvrez : http://urlshort.local/app"
echo ""
echo "Commandes utiles :"
echo "  minikube kubectl -- get all -n urlshort"
echo "  minikube kubectl -- get pods -n urlshort"
echo "  minikube kubectl -- logs -l app=shortener-service -n urlshort"
echo "  minikube kubectl -- logs -l app=analytics-service -n urlshort"
