# URLShort — Raccourcisseur d'URL Microservices

**FastAPI · gRPC · Docker · Kubernetes · Istio · PostgreSQL · React**

Projet M1 VMI — Architecture microservices complète avec service mesh, sécurité et frontend.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Navigateur (React)                  │
│              http://urlshort.local/app               │
└───────────────────────┬─────────────────────────────┘
                        │ HTTP
┌───────────────────────▼─────────────────────────────┐
│         Istio Ingress Gateway (urlshort.local)       │
│              VirtualService (routing)                │
│              PeerAuthentication (mTLS STRICT)        │
└──────────────┬──────────────────────┬───────────────┘
               │ /shorten /info /urls  │ /stats /analytics
               ▼                       ▼
┌──────────────────────┐   ┌──────────────────────────┐
│   shortener-service  │   │    analytics-service      │
│   FastAPI REST :8000 │──►│  FastAPI REST :8001       │
│   2 replicas         │gRPC│  gRPC server :50051      │
└──────────┬───────────┘   └────────────┬─────────────┘
           │                            │
┌──────────▼───────────┐   ┌────────────▼─────────────┐
│  PostgreSQL (urls)   │   │  PostgreSQL (analytics)   │
│  PVC 1Gi             │   │  PVC 1Gi                  │
└──────────────────────┘   └──────────────────────────┘
```

### Technologies utilisées

| Couche | Technologie |
|---|---|
| Microservices | Python 3.12 + FastAPI |
| Communication inter-services | **gRPC** (protobuf) — *bonus* |
| Containerisation | Docker + Docker Hub |
| Orchestration | Kubernetes (Minikube) |
| Service Mesh | **Istio** — Gateway, VirtualService, mTLS STRICT |
| Sécurité | RBAC K8s, NetworkPolicy (6 règles), PeerAuthentication |
| Auto-scaling | HPA — scale CPU 70%, min 2 / max 5 replicas |
| Base de données | PostgreSQL 16 avec PersistentVolumeClaim |
| Frontend | React 18 + Vite + nginx |

---

## Démarrage rapide — Docker Compose (local)

> Pas besoin de Kubernetes. Idéal pour tester rapidement.

```bash
docker-compose up --build
```

| Service | URL |
|---|---|
| Frontend React | http://localhost:9003 |
| Shortener API (Swagger) | http://localhost:9000/docs |
| Analytics API (Swagger) | http://localhost:9001/docs |

---

## Déploiement Kubernetes — Minikube

### 1. Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et lancé
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) installé
- Istio installé dans le cluster (voir ci-dessous)
- Compte Docker Hub

```powershell
# Démarrer Minikube avec les ressources nécessaires
minikube start --cpus=2 --memory=4096 --driver=docker --container-runtime=containerd

# Installer Istio dans le cluster (une seule fois)
istioctl install --set profile=demo -y
```

### 2. Build et push des images Docker


```bash
# Shortener (construit depuis la racine pour inclure le proto gRPC)
docker build -t massizelle/shortener-service:latest -f Dockerfile.shortener .

# Analytics
docker build -t massizelle/analytics-service:latest -f Dockerfile.analytics .

# Frontend (avec les URLs de l'ingress Istio)
docker build \
  --build-arg VITE_SHORTENER_URL=http://urlshort.local \
  --build-arg VITE_ANALYTICS_URL=http://urlshort.local \
  -t massizelle/urlshort-frontend:latest \
  frontend/

# Push sur Docker Hub
docker push massizelle/shortener-service:latest
docker push massizelle/analytics-service:latest
docker push massizelle/urlshort-frontend:latest
```

### 3. Appliquer les manifests Kubernetes

```bash
# Namespace + Istio (Gateway, VirtualService, mTLS)
minikube kubectl -- apply -f k8s/istio/istio-config.yaml

# RBAC (ServiceAccounts, Roles, RoleBindings, NetworkPolicy)
minikube kubectl -- apply -f k8s/rbac/rbac.yaml

# Bases de données PostgreSQL
minikube kubectl -- apply -f k8s/postgres-shortener/postgres-shortener.yaml
minikube kubectl -- apply -f k8s/postgres-analytics/postgres-analytics.yaml

# Attendre que PostgreSQL soit prêt
minikube kubectl -- wait --for=condition=ready pod -l app=postgres-shortener -n urlshort --timeout=120s
minikube kubectl -- wait --for=condition=ready pod -l app=postgres-analytics -n urlshort --timeout=120s

# Microservices et frontend
minikube kubectl -- apply -f k8s/shortener/shortener-deployment.yaml
minikube kubectl -- apply -f k8s/analytics/analytics-deployment.yaml
minikube kubectl -- apply -f k8s/shortener/frontend-deployment.yaml

# NetworkPolicies — isolation réseau inter-pods
minikube kubectl -- apply -f k8s/network-policies/network-policies.yaml

# HPA — auto-scaling CPU (nécessite metrics-server)
minikube addons enable metrics-server
minikube kubectl -- apply -f k8s/hpa/hpa.yaml
```

### 4. Exposer l'Istio Ingress Gateway

> Dans un terminal séparé, **laisser tourner en permanence** :

```bash
minikube tunnel
```

### 5. Configurer le fichier hosts

Ouvrir **Notepad en administrateur** et éditer `C:\Windows\System32\drivers\etc\hosts`, ajouter :

```
127.0.0.1  urlshort.local
```

### 6. Accès à l'application

| URL | Description |
|---|---|
| http://urlshort.local/app | **Frontend React** |
| http://urlshort.local/shorten | POST — Raccourcir une URL |
| http://urlshort.local/urls | GET — Liste toutes les URLs créées |
| http://urlshort.local/info/{code} | GET — Détails d'un code |
| http://urlshort.local/stats | GET — Statistiques de clics |
| http://urlshort.local/stats/{code} | GET — Stats d'un code spécifique |

---

## Tests et vérifications

### Vérifier l'état du cluster

```bash
# Tous les pods doivent être 2/2 Running
minikube kubectl -- get pods -n urlshort

# Vérifier les services
minikube kubectl -- get svc -n urlshort

# Vérifier le VirtualService Istio
minikube kubectl -- get virtualservice -n urlshort
```

Résultat attendu :
```
NAME                                  READY   STATUS    RESTARTS
analytics-service-xxx                 2/2     Running   0
frontend-xxx                          2/2     Running   0
postgres-analytics-xxx                2/2     Running   0
postgres-shortener-xxx                2/2     Running   0
shortener-service-xxx                 2/2     Running   0
shortener-service-xxx                 2/2     Running   0
```

### Tester les APIs (curl)

```bash
# 1. Health checks
curl http://urlshort.local/health
# → {"status":"ok","service":"shortener"}

# 2. Raccourcir une URL
curl -X POST http://urlshort.local/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.example.com/une-url-tres-longue"}'
# → {"short_code":"aB3xZ9","short_url":"http://urlshort.local/aB3xZ9","original_url":"..."}

# 3. Tester la redirection (remplace aB3xZ9 par le code obtenu)
curl -I http://urlshort.local/aB3xZ9
# → HTTP/1.1 302 Found
# → location: https://www.example.com/une-url-tres-longue

# 4. Voir les détails d'un code
curl http://urlshort.local/info/aB3xZ9
# → {"short_code":"aB3xZ9","original_url":"...","created_at":"..."}

# 5. Lister toutes les URLs créées
curl http://urlshort.local/urls
# → [{"short_code":"aB3xZ9","original_url":"...","short_url":"...","created_at":"..."}]

# 6. Stats de clics
curl http://urlshort.local/stats/aB3xZ9
# → {"short_code":"aB3xZ9","click_count":1,"recent_clicks":[...]}

# 7. Toutes les stats
curl http://urlshort.local/stats
# → [{"short_code":"aB3xZ9","click_count":1,...}]
```

### Vérifier le gRPC (communication inter-services)

```bash
# Les logs du shortener doivent montrer les appels gRPC après un clic
minikube kubectl -- logs -l app=shortener-service -n urlshort | grep gRPC
# → [gRPC] RecordClick OK  (ou silence si succès)

# Vérifier que le serveur gRPC analytics est actif
minikube kubectl -- logs -l app=analytics-service -n urlshort | grep gRPC
# → gRPC server listening on port 50051
```

### Vérifier la sécurité

```bash
# RBAC — ServiceAccounts et Roles
minikube kubectl -- get serviceaccounts -n urlshort
minikube kubectl -- get roles,rolebindings -n urlshort

# mTLS STRICT — PeerAuthentication
minikube kubectl -- get peerauthentication -n urlshort
# → default   STRICT

# NetworkPolicy — 6 règles d'isolation inter-pods
minikube kubectl -- get networkpolicy -n urlshort

# DestinationRules — mTLS côté client
minikube kubectl -- get destinationrule -n urlshort
```

### Vérifier l'auto-scaling (HPA)

```bash
# État des HPA (CPU actuel / seuil)
minikube kubectl -- get hpa -n urlshort
# → shortener-hpa   cpu: 15%/70%   MINPODS: 2   MAXPODS: 5   REPLICAS: 2
# → analytics-hpa   cpu: 17%/70%   MINPODS: 2   MAXPODS: 5   REPLICAS: 2

# Métriques CPU en temps réel
minikube kubectl -- top pods -n urlshort
```

### Vérifier la base de données

```bash
# Contenu de la base shortener
minikube kubectl -- exec deploy/postgres-shortener -n urlshort -- \
  psql -U shortener_user -d urlshortener -c "SELECT * FROM urls;"

# Contenu de la base analytics
minikube kubectl -- exec deploy/postgres-analytics -n urlshort -- \
  psql -U analytics_user -d analytics -c "SELECT * FROM url_stats;"
```

---

## Structure du projet

```
urlshortener_final/
├── proto/
│   └── analytics.proto              # Contrat gRPC partagé (ClickRequest, StatsResponse...)
├── shortener-service/
│   ├── main.py                      # FastAPI REST + client gRPC vers analytics
│   ├── requirements.txt
│   ├── start.sh                     # Génère les stubs gRPC puis lance uvicorn
│   └── Dockerfile                   # Build depuis le dossier service
├── analytics-service/
│   ├── main.py                      # FastAPI REST + serveur gRPC (thread daemon)
│   ├── requirements.txt
│   ├── start.sh
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx                  # UI React (raccourcir + dashboard)
│   │   ├── App.css
│   │   └── main.jsx
│   ├── index.html
│   ├── vite.config.js
│   ├── nginx.conf                   # SPA routing (try_files)
│   └── Dockerfile                   # Multi-stage : build Vite → nginx
├── k8s/
│   ├── istio/
│   │   └── istio-config.yaml        # Namespace, Gateway, VirtualService, mTLS, DestinationRules
│   ├── rbac/
│   │   └── rbac.yaml                # ServiceAccounts, Roles, RoleBindings, NetworkPolicy
│   ├── postgres-shortener/
│   │   └── postgres-shortener.yaml  # Deployment, Service, PVC, Secret
│   ├── postgres-analytics/
│   │   └── postgres-analytics.yaml
│   ├── shortener/
│   │   ├── shortener-deployment.yaml
│   │   └── frontend-deployment.yaml
│   ├── network-policies/
│   │   └── network-policies.yaml    # 6 NetworkPolicies (default-deny + isolation par service)
│   ├── hpa/
│   │   └── hpa.yaml                 # HPA shortener + analytics (CPU 70%, min 2 / max 5)
│   └── analytics/
│       └── analytics-deployment.yaml
├── Dockerfile.shortener             # Build depuis la racine (contexte inclut proto/)
├── Dockerfile.analytics
├── docker-compose.yml               # Dev local sans Kubernetes
├── deploy.sh                        # Script de déploiement automatique Minikube
└── README.md
```

---
