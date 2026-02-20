#!/bin/bash
# Deploy HR Intelligence to EC2

set -e

EC2_HOST="3.110.62.153"
EC2_USER="ubuntu"
DEPLOY_DIR="/opt/hr-intelligence"
SSH_KEY="${SSH_KEY:-scripts/keka/deploy/keka-deploy.pem}"

echo "🚀 Deploying HR Intelligence to $EC2_HOST..."

# SSH and deploy
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$EC2_USER@$EC2_HOST" << 'DEPLOY'
set -e
cd /opt/hr-intelligence

# Pull latest
git pull origin main

# Build and restart
docker compose -f docker-compose.yml -f docker-compose.prod.yml build
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Wait and health check
sleep 10
if curl -sf http://localhost:8000/api/v1/health > /dev/null; then
    echo "✅ Deploy successful! Health check passed."
else
    echo "❌ Health check failed!"
    docker compose logs --tail=50 api
    exit 1
fi
DEPLOY

echo "✅ Deployment complete — https://hr.cfai.in"
