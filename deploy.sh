#!/bin/bash

USER=root
HOST=vps
DIR=/opt/interview-assistant

echo "deploy to $HOST..."

tar -czf - --exclude='venv' --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='redis-data' ./src/ | ssh $USER@$HOST "tar -xzf - -C $DIR"

scp ./src/.env $USER@$HOST:$DIR/src/.env

ssh $USER@$HOST << EOF
  cd $DIR/src
  echo "Containers building..."
  docker compose down
  docker compose up -d --build
  
  echo "Cleaning up old images..."
  docker image prune -f
EOF

echo "Deployment completed"