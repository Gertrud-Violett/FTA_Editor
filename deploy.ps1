# FTA/ETA Editor - Build and Deployment Script (PowerShell)
# Version: 2.2.1

param(
    [Parameter(Position=0)]
    [string]$Action = "help",
    
    [Parameter(Position=1)]
    [string]$Username = ""
)

$VERSION = "2.2.1"
$IMAGE_NAME = "fta-editor"

function Print-Header {
    Write-Host "=====================================" -ForegroundColor Cyan
    Write-Host "FTA/ETA Editor Build & Deploy Script" -ForegroundColor Cyan
    Write-Host "Version: $VERSION" -ForegroundColor Cyan
    Write-Host "=====================================" -ForegroundColor Cyan
    Write-Host ""
}

function Print-Success {
    param([string]$Message)
    Write-Host "✓ $Message" -ForegroundColor Green
}

function Print-Error {
    param([string]$Message)
    Write-Host "✗ $Message" -ForegroundColor Red
}

function Print-Info {
    param([string]$Message)
    Write-Host "→ $Message" -ForegroundColor Yellow
}

Print-Header

switch ($Action.ToLower()) {
    "build" {
        Print-Info "Building Docker image: ${IMAGE_NAME}:${VERSION}"
        docker build -t "${IMAGE_NAME}:${VERSION}" -t "${IMAGE_NAME}:latest" .
        if ($LASTEXITCODE -eq 0) {
            Print-Success "Docker image built successfully"
        } else {
            Print-Error "Build failed"
            exit 1
        }
    }
    
    "run" {
        Print-Info "Running FTA/ETA Editor..."
        docker-compose up
    }
    
    "start" {
        Print-Info "Starting FTA/ETA Editor in background..."
        docker-compose up -d
        if ($LASTEXITCODE -eq 0) {
            Print-Success "Application started. Use 'docker-compose logs -f' to view logs"
        }
    }
    
    "stop" {
        Print-Info "Stopping FTA/ETA Editor..."
        docker-compose down
        if ($LASTEXITCODE -eq 0) {
            Print-Success "Application stopped"
        }
    }
    
    "restart" {
        Print-Info "Restarting FTA/ETA Editor..."
        docker-compose down
        docker-compose up -d
        if ($LASTEXITCODE -eq 0) {
            Print-Success "Application restarted"
        }
    }
    
    "rebuild" {
        Print-Info "Rebuilding and restarting..."
        docker-compose down
        docker build -t "${IMAGE_NAME}:${VERSION}" -t "${IMAGE_NAME}:latest" .
        docker-compose up -d
        if ($LASTEXITCODE -eq 0) {
            Print-Success "Application rebuilt and restarted"
        }
    }
    
    "logs" {
        Print-Info "Showing application logs (Ctrl+C to exit)..."
        docker-compose logs -f
    }
    
    "test" {
        Print-Info "Running tests..."
        python -m pytest tests/ -v
        if ($LASTEXITCODE -eq 0) {
            Print-Success "Tests completed"
        }
    }
    
    "clean" {
        Print-Info "Cleaning up Docker resources..."
        docker-compose down -v
        docker system prune -f
        Print-Success "Cleanup completed"
    }
    
    "push" {
        if ([string]::IsNullOrWhiteSpace($Username)) {
            Print-Error "Please provide Docker Hub username: .\deploy.ps1 push <username>"
            exit 1
        }
        Print-Info "Tagging and pushing to Docker Hub..."
        docker tag "${IMAGE_NAME}:${VERSION}" "${Username}/${IMAGE_NAME}:${VERSION}"
        docker tag "${IMAGE_NAME}:${VERSION}" "${Username}/${IMAGE_NAME}:latest"
        docker push "${Username}/${IMAGE_NAME}:${VERSION}"
        docker push "${Username}/${IMAGE_NAME}:latest"
        if ($LASTEXITCODE -eq 0) {
            Print-Success "Image pushed to Docker Hub"
        }
    }
    
    "install" {
        Print-Info "Installing Python dependencies..."
        pip install -r requirements.txt
        if ($LASTEXITCODE -eq 0) {
            Print-Success "Dependencies installed"
        }
        Print-Info "Checking Graphviz installation..."
        $dotPath = Get-Command dot -ErrorAction SilentlyContinue
        if ($dotPath) {
            Print-Success "Graphviz is installed at: $($dotPath.Source)"
        } else {
            Print-Error "Graphviz not found. Please install from https://graphviz.org/download/"
            Print-Info "After installation, add Graphviz to your PATH"
        }
    }
    
    "status" {
        Print-Info "Checking Docker container status..."
        docker-compose ps
    }
    
    default {
        Write-Host "FTA/ETA Editor Build & Deploy Script" -ForegroundColor White
        Write-Host ""
        Write-Host "Usage: .\deploy.ps1 [command] [options]" -ForegroundColor White
        Write-Host ""
        Write-Host "Commands:" -ForegroundColor Yellow
        Write-Host "  build         Build Docker image"
        Write-Host "  run           Run application with Docker Compose"
        Write-Host "  start         Start application in background"
        Write-Host "  stop          Stop running application"
        Write-Host "  restart       Restart application"
        Write-Host "  rebuild       Rebuild and restart application"
        Write-Host "  logs          Show application logs"
        Write-Host "  test          Run test suite"
        Write-Host "  clean         Clean up Docker resources"
        Write-Host "  push <user>   Push image to Docker Hub"
        Write-Host "  install       Install Python dependencies locally"
        Write-Host "  status        Show container status"
        Write-Host "  help          Show this help message"
        Write-Host ""
        Write-Host "Examples:" -ForegroundColor Cyan
        Write-Host "  .\deploy.ps1 build          # Build Docker image"
        Write-Host "  .\deploy.ps1 start          # Start in background"
        Write-Host "  .\deploy.ps1 logs           # View logs"
        Write-Host "  .\deploy.ps1 push myuser    # Push to Docker Hub"
    }
}
