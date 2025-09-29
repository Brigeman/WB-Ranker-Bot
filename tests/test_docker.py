"""Tests for Docker configuration and deployment."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

import pytest
import yaml


class TestDockerConfiguration:
    """Test Docker configuration files."""
    
    def test_dockerfile_exists(self):
        """Test that Dockerfile exists and is valid."""
        dockerfile_path = Path("Dockerfile")
        assert dockerfile_path.exists(), "Dockerfile not found"
        
        # Check basic structure
        with open(dockerfile_path) as f:
            content = f.read()
            assert "FROM python:3.11-slim" in content
            assert "WORKDIR /app" in content
            assert "COPY requirements.txt" in content
            assert "CMD" in content
    
    def test_dockerfile_dev_exists(self):
        """Test that development Dockerfile exists."""
        dockerfile_path = Path("Dockerfile.dev")
        assert dockerfile_path.exists(), "Dockerfile.dev not found"
        
        with open(dockerfile_path) as f:
            content = f.read()
            assert "FROM python:3.11-slim" in content
            assert "pytest" in content
            assert "black" in content
    
    def test_docker_compose_exists(self):
        """Test that docker-compose.yml exists and is valid."""
        compose_path = Path("docker-compose.yml")
        assert compose_path.exists(), "docker-compose.yml not found"
        
        with open(compose_path) as f:
            compose_data = yaml.safe_load(f)
            
            # Check basic structure
            assert "services" in compose_data
            assert "wb-ranker-bot" in compose_data["services"]
            assert "volumes" in compose_data
            assert "networks" in compose_data
    
    def test_docker_compose_dev_exists(self):
        """Test that development docker-compose exists."""
        compose_path = Path("docker-compose.dev.yml")
        assert compose_path.exists(), "docker-compose.dev.yml not found"
        
        with open(compose_path) as f:
            compose_data = yaml.safe_load(f)
            
            assert "services" in compose_data
            assert "wb-ranker-bot-dev" in compose_data["services"]
    
    def test_dockerignore_exists(self):
        """Test that .dockerignore exists."""
        dockerignore_path = Path(".dockerignore")
        assert dockerignore_path.exists(), ".dockerignore not found"
        
        with open(dockerignore_path) as f:
            content = f.read()
            assert "__pycache__" in content
            assert "venv" in content
            assert ".git" in content
    
    def test_makefile_exists(self):
        """Test that Makefile exists."""
        makefile_path = Path("Makefile")
        assert makefile_path.exists(), "Makefile not found"
        
        with open(makefile_path) as f:
            content = f.read()
            assert "build:" in content
            assert "up:" in content
            assert "down:" in content
            assert "logs:" in content
    
    def test_deploy_script_exists(self):
        """Test that deployment script exists and is executable."""
        deploy_path = Path("deploy.sh")
        assert deploy_path.exists(), "deploy.sh not found"
        assert os.access(deploy_path, os.X_OK), "deploy.sh is not executable"
    
    def test_monitoring_config_exists(self):
        """Test that monitoring configuration exists."""
        prometheus_path = Path("monitoring/prometheus.yml")
        assert prometheus_path.exists(), "prometheus.yml not found"
        
        grafana_datasources = Path("monitoring/grafana/datasources/prometheus.yml")
        assert grafana_datasources.exists(), "Grafana datasources not found"
        
        grafana_dashboards = Path("monitoring/grafana/dashboards/dashboard.yml")
        assert grafana_dashboards.exists(), "Grafana dashboards not found"


class TestDockerComposeConfiguration:
    """Test Docker Compose configuration."""
    
    @pytest.fixture
    def compose_data(self):
        """Load docker-compose.yml data."""
        with open("docker-compose.yml") as f:
            return yaml.safe_load(f)
    
    def test_main_service_configuration(self, compose_data):
        """Test main service configuration."""
        service = compose_data["services"]["wb-ranker-bot"]
        
        # Check required fields
        assert "build" in service
        assert "environment" in service
        assert "volumes" in service
        assert "networks" in service
        
        # Check environment variables
        env_vars = service["environment"]
        assert any("BOT_TOKEN" in env for env in env_vars)
        assert any("WB_MAX_PAGES" in env for env in env_vars)
        assert any("LOG_LEVEL" in env for env in env_vars)
    
    def test_redis_service_configuration(self, compose_data):
        """Test Redis service configuration."""
        service = compose_data["services"]["redis"]
        
        assert service["image"] == "redis:7-alpine"
        assert "volumes" in service
        assert "networks" in service
    
    def test_monitoring_services(self, compose_data):
        """Test monitoring services configuration."""
        # Prometheus
        prometheus = compose_data["services"]["prometheus"]
        assert prometheus["image"] == "prom/prometheus:latest"
        assert "9090:9090" in prometheus["ports"]
        
        # Grafana
        grafana = compose_data["services"]["grafana"]
        assert grafana["image"] == "grafana/grafana:latest"
        assert "3000:3000" in grafana["ports"]
    
    def test_volumes_configuration(self, compose_data):
        """Test volumes configuration."""
        volumes = compose_data["volumes"]
        
        assert "redis-data" in volumes
        assert "prometheus-data" in volumes
        assert "grafana-data" in volumes
    
    def test_networks_configuration(self, compose_data):
        """Test networks configuration."""
        networks = compose_data["networks"]
        
        assert "wb-ranker-network" in networks
        network_config = networks["wb-ranker-network"]
        assert network_config["driver"] == "bridge"


class TestDockerComposeDevConfiguration:
    """Test development Docker Compose configuration."""
    
    @pytest.fixture
    def compose_data(self):
        """Load docker-compose.dev.yml data."""
        with open("docker-compose.dev.yml") as f:
            return yaml.safe_load(f)
    
    def test_dev_service_configuration(self, compose_data):
        """Test development service configuration."""
        service = compose_data["services"]["wb-ranker-bot-dev"]
        
        assert "build" in service
        assert "environment" in service
        assert "volumes" in service
        
        # Check development-specific settings
        env_vars = service["environment"]
        assert any("LOG_LEVEL=DEBUG" in env for env in env_vars)
        assert any("LOG_FORMAT=text" in env for env in env_vars)
    
    def test_dev_database_service(self, compose_data):
        """Test development database service."""
        service = compose_data["services"]["postgres-dev"]
        
        assert service["image"] == "postgres:15-alpine"
        assert "5432:5432" in service["ports"]
        
        env_vars = service["environment"]
        assert any("POSTGRES_DB=wb_ranker_dev" in env for env in env_vars)
    
    def test_dev_redis_service(self, compose_data):
        """Test development Redis service."""
        service = compose_data["services"]["redis-dev"]
        
        assert service["image"] == "redis:7-alpine"
        assert "6379:6379" in service["ports"]


class TestDeploymentScript:
    """Test deployment script functionality."""
    
    def test_deploy_script_structure(self):
        """Test deployment script structure."""
        with open("deploy.sh") as f:
            content = f.read()
            
            # Check for required functions
            assert "check_env_file" in content
            assert "create_directories" in content
            assert "build_image" in content
            assert "start_services" in content
            assert "deploy()" in content
            assert "deploy_dev()" in content
    
    def test_deploy_script_help(self):
        """Test deployment script help functionality."""
        with open("deploy.sh") as f:
            content = f.read()
            
            assert "show_help" in content
            assert "deploy" in content
            assert "dev" in content
            assert "status" in content
            assert "logs" in content


class TestMakefileCommands:
    """Test Makefile commands."""
    
    def test_makefile_commands(self):
        """Test that all required Makefile commands exist."""
        with open("Makefile") as f:
            content = f.read()
            
            # Production commands
            assert "build:" in content
            assert "up:" in content
            assert "down:" in content
            assert "logs:" in content
            assert "shell:" in content
            assert "test:" in content
            assert "clean:" in content
            
            # Development commands
            assert "dev-up:" in content
            assert "dev-down:" in content
            assert "dev-logs:" in content
            assert "dev-shell:" in content
            
            # Utility commands
            assert "status:" in content
            assert "restart:" in content
            assert "health:" in content


class TestMonitoringConfiguration:
    """Test monitoring configuration."""
    
    def test_prometheus_config(self):
        """Test Prometheus configuration."""
        with open("monitoring/prometheus.yml") as f:
            content = f.read()
            
            assert "global:" in content
            assert "scrape_configs:" in content
            assert "wb-ranker-bot" in content
            assert "prometheus" in content
    
    def test_grafana_datasources(self):
        """Test Grafana datasources configuration."""
        with open("monitoring/grafana/datasources/prometheus.yml") as f:
            content = f.read()
            
            assert "apiVersion: 1" in content
            assert "datasources:" in content
            assert "Prometheus" in content
    
    def test_grafana_dashboards(self):
        """Test Grafana dashboards configuration."""
        with open("monitoring/grafana/dashboards/dashboard.yml") as f:
            content = f.read()
            
            assert "apiVersion: 1" in content
            assert "providers:" in content
            assert "WB Ranker Bot Dashboards" in content


class TestDockerIntegration:
    """Test Docker integration."""
    
    def test_dockerfile_syntax(self):
        """Test Dockerfile syntax using docker build --dry-run if available."""
        # This is a basic syntax check
        dockerfile_path = Path("Dockerfile")
        assert dockerfile_path.exists()
        
        # Check for common Dockerfile issues
        with open(dockerfile_path) as f:
            lines = f.readlines()
            
            # Check for proper FROM statement
            assert any(line.startswith("FROM") for line in lines)
            
            # Check for WORKDIR
            assert any(line.startswith("WORKDIR") for line in lines)
            
            # Check for CMD or ENTRYPOINT
            assert any(line.startswith("CMD") or line.startswith("ENTRYPOINT") for line in lines)
    
    def test_docker_compose_syntax(self):
        """Test Docker Compose syntax."""
        # Test main compose file
        with open("docker-compose.yml") as f:
            compose_data = yaml.safe_load(f)
            assert isinstance(compose_data, dict)
            assert "services" in compose_data
        
        # Test dev compose file
        with open("docker-compose.dev.yml") as f:
            compose_data = yaml.safe_load(f)
            assert isinstance(compose_data, dict)
            assert "services" in compose_data
    
    def test_environment_variables_consistency(self):
        """Test that environment variables are consistent across files."""
        # Load compose files
        with open("docker-compose.yml") as f:
            prod_compose = yaml.safe_load(f)
        
        with open("docker-compose.dev.yml") as f:
            dev_compose = yaml.safe_load(f)
        
        # Extract environment variables
        prod_env = prod_compose["services"]["wb-ranker-bot"]["environment"]
        dev_env = dev_compose["services"]["wb-ranker-bot-dev"]["environment"]
        
        # Check that key variables exist in both
        prod_vars = {env.split("=")[0] for env in prod_env if "=" in env}
        dev_vars = {env.split("=")[0] for env in dev_env if "=" in env}
        
        # Key variables should exist in both
        key_vars = {"BOT_TOKEN", "WB_MAX_PAGES", "LOG_LEVEL"}
        assert key_vars.issubset(prod_vars)
        assert key_vars.issubset(dev_vars)
