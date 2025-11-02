#!/usr/bin/env python3
"""
Test script for reliability and performance features.
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from cache import cache_manager, init_cache
from metrics import metrics_collector
from monitoring import health_check


async def test_cache():
    """Test Redis cache functionality"""
    print("Testing Redis cache...")

    try:
        # Test basic cache operations
        test_key = "test_key"
        test_data = {"message": "Hello, World!", "number": 42}

        # Set data
        success = await cache_manager.set_user_data(0, test_key, test_data)
        print(f"Cache set result: {success}")

        # Get data
        retrieved_data = await cache_manager.get_user_data(0, test_key)
        print(f"Cache get result: {retrieved_data}")

        # Check if data matches
        if retrieved_data == test_data:
            print("✅ Cache test passed")
            return True
        else:
            print("❌ Cache test failed - data mismatch")
            return False

    except Exception as e:
        print(f"❌ Cache test failed with error: {e}")
        return False


async def test_metrics():
    """Test Prometheus metrics collection"""
    print("Testing Prometheus metrics...")

    try:
        # Record some test metrics
        metrics_collector.record_request("GET", "/test", "200", 0.1)
        metrics_collector.record_transcription("completed", False, 2.5)
        metrics_collector.record_cache_hit("transcription")
        metrics_collector.record_error("TestError", "test_module")

        print("✅ Metrics recording test passed")
        return True

    except Exception as e:
        print(f"❌ Metrics test failed with error: {e}")
        return False


def test_monitoring():
    """Test monitoring health check"""
    print("Testing monitoring health check...")

    try:
        health = health_check()
        print(f"Health check result: {health}")

        if health.get('status') in ['healthy', 'unhealthy']:
            print("✅ Monitoring test passed")
            return True
        else:
            print("❌ Monitoring test failed - invalid health status")
            return False

    except Exception as e:
        print(f"❌ Monitoring test failed with error: {e}")
        return False


async def main():
    """Run all tests"""
    print("🚀 Starting reliability and performance tests...\n")

    # Initialize cache
    await init_cache()

    # Run tests
    tests = [
        ("Cache", test_cache),
        ("Metrics", test_metrics),
        ("Monitoring", test_monitoring),
    ]

    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        print(f"Running {test_name} test...")
        print('='*50)

        if asyncio.iscoroutinefunction(test_func):
            result = await test_func()
        else:
            result = test_func()

        results.append((test_name, result))

    # Summary
    print(f"\n{'='*50}")
    print("TEST SUMMARY")
    print('='*50)

    passed = 0
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Reliability features are working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
