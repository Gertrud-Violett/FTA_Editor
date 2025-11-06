#!/usr/bin/env python3
"""
FTA Editor Setup Script
Helps users install dependencies and run the application
"""

import sys
import subprocess
import os
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 8):
        print("❌ Error: Python 3.8 or higher required")
        print(f"   Current version: {sys.version}")
        return False
    print(f"✅ Python {sys.version.split()[0]} detected")
    return True

def check_graphviz():
    """Check if Graphviz is installed"""
    try:
        subprocess.run(["dot", "-V"], capture_output=True, check=True)
        print("✅ Graphviz is installed")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ Graphviz not found")
        print("   Install from: https://graphviz.org/download/")
        return False

def install_requirements():
    """Install Python requirements"""
    try:
        print("📦 Installing Python dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                      check=True)
        print("✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def run_tests():
    """Run test suite"""
    try:
        print("🧪 Running tests...")
        result = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"], 
                               capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ All tests passed")
            return True
        else:
            print("❌ Some tests failed")
            print(result.stdout)
            return False
    except FileNotFoundError:
        print("⚠️  pytest not found, skipping tests")
        return True

def run_application():
    """Launch the FTA Editor"""
    try:
        print("🚀 Launching FTA Editor...")
        subprocess.run([sys.executable, "src/FTA_Editor_UI.py"])
    except KeyboardInterrupt:
        print("\n👋 Application closed by user")
    except Exception as e:
        print(f"❌ Failed to launch application: {e}")

def main():
    """Main setup routine"""
    print("🔧 FTA Editor Setup")
    print("=" * 30)
    
    # Check prerequisites
    if not check_python_version():
        sys.exit(1)
    
    if not check_graphviz():
        print("⚠️  Graphviz is required for diagram rendering")
        choice = input("Continue anyway? (y/N): ").lower()
        if choice != 'y':
            sys.exit(1)
    
    # Install dependencies
    if not install_requirements():
        sys.exit(1)
    
    # Run tests
    run_tests()
    
    # Launch application
    print("\n" + "=" * 30)
    choice = input("Launch FTA Editor now? (Y/n): ").lower()
    if choice != 'n':
        run_application()
    
    print("\n✅ Setup complete!")
    print("   To run later: python src/FTA_Editor_UI.py")

if __name__ == "__main__":
    main()