#!/bin/bash
# FTA/ETA Editor - Build and Deployment Script
# Version: 2.2.1

set -e

VERSION="2.2.1"
IMAGE_NAME="fta-editor"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================"
echo "FTA/ETA Editor Build & Deploy Script"
echo "Version: $VERSION"
echo "======================================"
echo ""

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Parse command line arguments
ACTION=${1:-help}

case "$ACTION" in
    build)
        print_info "Building Docker image: $IMAGE_NAME:$VERSION"
        docker build -t $IMAGE_NAME:$VERSION -t $IMAGE_NAME:latest .
        print_success "Docker image built successfully"
        ;;
    
    run)
        print_info "Running FTA/ETA Editor..."
        docker-compose up
        ;;
    
    start)
        print_info "Starting FTA/ETA Editor in background..."
        docker-compose up -d
        print_success "Application started. Use 'docker-compose logs -f' to view logs"
        ;;
    
    stop)
        print_info "Stopping FTA/ETA Editor..."
        docker-compose down
        print_success "Application stopped"
        ;;
    
    restart)
        print_info "Restarting FTA/ETA Editor..."
        docker-compose down
        docker-compose up -d
        print_success "Application restarted"
        ;;
    
    rebuild)
        print_info "Rebuilding and restarting..."
        docker-compose down
        docker build -t $IMAGE_NAME:$VERSION -t $IMAGE_NAME:latest .
        docker-compose up -d
        print_success "Application rebuilt and restarted"
        ;;
    
    logs)
        print_info "Showing application logs (Ctrl+C to exit)..."
        docker-compose logs -f
        ;;
    
    test)
        print_info "Running tests..."
        python -m pytest tests/ -v
        print_success "Tests completed"
        ;;
    
    clean)
        print_info "Cleaning up Docker resources..."
        docker-compose down -v
        docker system prune -f
        print_success "Cleanup completed"
        ;;
    
    push)
        if [ -z "$2" ]; then
            print_error "Please provide Docker Hub username: ./deploy.sh push <username>"
            exit 1
        fi
        USERNAME=$2
        print_info "Tagging and pushing to Docker Hub..."
        docker tag $IMAGE_NAME:$VERSION $USERNAME/$IMAGE_NAME:$VERSION
        docker tag $IMAGE_NAME:$VERSION $USERNAME/$IMAGE_NAME:latest
        docker push $USERNAME/$IMAGE_NAME:$VERSION
        docker push $USERNAME/$IMAGE_NAME:latest
        print_success "Image pushed to Docker Hub"
        ;;
    
    install)
        print_info "Installing Python dependencies..."
        pip install -r requirements.txt
        print_success "Dependencies installed"
        print_info "Checking Graphviz installation..."
        if command -v dot &> /dev/null; then
            print_success "Graphviz is installed"
        else
            print_error "Graphviz not found. Please install from https://graphviz.org/download/"
        fi
        ;;
    
    status)
        print_info "Checking Docker container status..."
        docker-compose ps
        ;;
    
    help|*)
        echo "FTA/ETA Editor Build & Deploy Script"
        echo ""
        echo "Usage: ./deploy.sh [command]"
        echo ""
        echo "Commands:"
        echo "  build         Build Docker image"
        echo "  run           Run application with Docker Compose"
        echo "  start         Start application in background"
        echo "  stop          Stop running application"
        echo "  restart       Restart application"
        echo "  rebuild       Rebuild and restart application"
        echo "  logs          Show application logs"
        echo "  test          Run test suite"
        echo "  clean         Clean up Docker resources"
        echo "  push <user>   Push image to Docker Hub"
        echo "  install       Install Python dependencies locally"
        echo "  status        Show container status"
        echo "  help          Show this help message"
        echo ""
        echo "Examples:"
        echo "  ./deploy.sh build          # Build Docker image"
        echo "  ./deploy.sh start          # Start in background"
        echo "  ./deploy.sh logs           # View logs"
        echo "  ./deploy.sh push myuser    # Push to Docker Hub"
        ;;
esac
