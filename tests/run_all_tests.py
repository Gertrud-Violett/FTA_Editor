#!/usr/bin/env python3
"""
Run all tests for FTA/ETA Editor
"""
import sys
import subprocess
from pathlib import Path

def run_tests():
    """Run all test files"""
    test_dir = Path(__file__).parent
    test_files = [
        "test_core_module.py",
        "test_probability_calculation.py",
        "test_eta_mode.py",
        "test_excel_export.py",
    ]
    
    print("=" * 70)
    print("FTA/ETA EDITOR - TEST SUITE")
    print("=" * 70)
    print()
    
    passed = 0
    failed = 0
    
    for test_file in test_files:
        test_path = test_dir / test_file
        if not test_path.exists():
            print(f"⚠️  Skipping {test_file} (not found)")
            continue
            
        print(f"Running {test_file}...")
        print("-" * 70)
        
        result = subprocess.run(
            [sys.executable, str(test_path)],
            cwd=test_dir.parent,
            capture_output=False
        )
        
        if result.returncode == 0:
            print(f"✅ {test_file} PASSED")
            passed += 1
        else:
            print(f"❌ {test_file} FAILED")
            failed += 1
        
        print()
    
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {passed}/{passed + failed}")
    print(f"Failed: {failed}/{passed + failed}")
    print()
    
    if failed == 0:
        print("✅ ALL TESTS PASSED!")
        return 0
    else:
        print(f"❌ {failed} TEST(S) FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(run_tests())
