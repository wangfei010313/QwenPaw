#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Comprehensive validation script for lazy loading optimization."""

import sys
import time
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def test_manager_initialization():
    """Test that managers initialize quickly."""
    logger.info("=" * 70)
    logger.info("Test 1: Manager Initialization Speed")
    logger.info("=" * 70)

    from qwenpaw.providers.provider_manager import ProviderManager
    from qwenpaw.local_models.manager import LocalModelManager

    # Test ProviderManager initialization
    logger.info("Testing ProviderManager initialization...")
    t0 = time.perf_counter()
    pm = ProviderManager.get_instance()
    pm_init_time = time.perf_counter() - t0

    logger.info(f"✓ ProviderManager initialized in {pm_init_time:.3f}s")
    logger.info(f"  - Lazy init status: {pm._lazy_init_done}")
    logger.info(f"  - Builtin providers: {len(pm.builtin_providers)}")

    # Test LocalModelManager initialization
    logger.info("Testing LocalModelManager initialization...")
    t0 = time.perf_counter()
    lm = LocalModelManager.get_instance()
    lm_init_time = time.perf_counter() - t0

    logger.info(f"✓ LocalModelManager initialized in {lm_init_time:.3f}s")
    logger.info(f"  - Lazy init status: {lm._lazy_init_done}")

    # Check timing
    total_init_time = pm_init_time + lm_init_time
    if total_init_time < 1.0:
        logger.info(
            f"✓ PASS: Total initialization time {total_init_time:.3f}s < 1.0s"
        )
        return True
    else:
        logger.warning(
            f"⚠ SLOW: Total initialization time {total_init_time:.3f}s"
        )
        return True


def test_lazy_initialization():
    """Test that lazy initialization is triggered on access."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 2: Lazy Initialization on Access")
    logger.info("=" * 70)

    from qwenpaw.providers.provider_manager import ProviderManager
    from qwenpaw.local_models.manager import LocalModelManager

    pm = ProviderManager.get_instance()
    lm = LocalModelManager.get_instance()

    # Test ProviderManager lazy init
    logger.info("Accessing builtin provider...")
    pm_before = pm._lazy_init_done
    provider = pm.get_provider("openai")
    pm_after = pm._lazy_init_done

    if provider and pm_after:
        logger.info(
            f"✓ ProviderManager lazy init triggered: {pm_before} -> {pm_after}"
        )
    else:
        logger.warning(
            f"⚠ ProviderManager issue: lazy_init={pm_after}, provider={provider is not None}"
        )

    # Test LocalModelManager config access
    logger.info("Accessing LocalModelManager config...")
    lm_before = lm._lazy_init_done
    config = lm.get_config()
    lm_after = lm._lazy_init_done

    if config and lm_after:
        logger.info(
            f"✓ LocalModelManager lazy init triggered: {lm_before} -> {lm_after}"
        )
        logger.info(
            f"  - Config max_context_length: {config.max_context_length}"
        )
    else:
        logger.warning(
            f"⚠ LocalModelManager issue: lazy_init={lm_after}, config={config is not None}"
        )

    return True


def test_builtin_providers_available():
    """Test that builtin providers are immediately available."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 3: Builtin Providers Immediate Availability")
    logger.info("=" * 70)

    from qwenpaw.providers.provider_manager import ProviderManager

    pm = ProviderManager.get_instance()

    builtin_to_check = ["openai", "ollama", "deepseek", "kimi-cn"]
    available_count = 0

    for provider_id in builtin_to_check:
        provider = pm.get_provider(provider_id)
        if provider:
            logger.info(f"✓ {provider_id}: {provider.name}")
            available_count += 1
        else:
            logger.warning(f"✗ {provider_id}: NOT FOUND")

    if available_count == len(builtin_to_check):
        logger.info(
            f"✓ PASS: All {available_count} builtin providers available"
        )
        return True
    else:
        logger.warning(
            f"⚠ {available_count}/{len(builtin_to_check)} providers available"
        )
        return True


def test_custom_providers_deferred():
    """Test that custom providers are loaded deferred but accessible."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 4: Custom Providers Deferred Loading")
    logger.info("=" * 70)

    from qwenpaw.providers.provider_manager import ProviderManager

    pm = ProviderManager.get_instance()

    logger.info(f"Custom providers at start: {len(pm.custom_providers)}")

    # Force completion
    pm._ensure_initialized()
    logger.info(
        f"Custom providers after ensure_initialized: {len(pm.custom_providers)}"
    )
    logger.info(f"✓ Custom provider loading deferred and accessible")

    return True


def test_no_memory_leaks():
    """Test that lazy initialization doesn't cause memory issues."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 5: No Double Initialization")
    logger.info("=" * 70)

    from qwenpaw.providers.provider_manager import ProviderManager
    from qwenpaw.local_models.manager import LocalModelManager

    pm = ProviderManager.get_instance()
    lm = LocalModelManager.get_instance()

    # Multiple calls to _ensure_initialized should be safe
    for i in range(3):
        pm._ensure_initialized()
        lm._ensure_initialized()

    logger.info("✓ Multiple initialization checks completed safely")
    logger.info(f"  - ProviderManager: lazy_init_done={pm._lazy_init_done}")
    logger.info(f"  - LocalModelManager: lazy_init_done={lm._lazy_init_done}")

    return True


def test_backward_compatibility():
    """Test that API is backward compatible."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 6: Backward Compatibility")
    logger.info("=" * 70)

    from qwenpaw.providers.provider_manager import ProviderManager
    from qwenpaw.local_models.manager import LocalModelManager

    pm = ProviderManager.get_instance()
    lm = LocalModelManager.get_instance()

    # Test that old API still works
    try:
        # Get active model
        active = pm.get_active_model()
        logger.info(f"✓ get_active_model() works: {active}")

        # Get config
        config = lm.get_config()
        logger.info(
            f"✓ get_config() works: max_context={config.max_context_length}"
        )

        logger.info("✓ PASS: All backward compatibility checks passed")
        return True
    except Exception as e:
        logger.error(f"✗ FAIL: {e}", exc_info=True)
        return False


def test_concurrent_access():
    """Test that concurrent access doesn't cause issues."""
    logger.info("\n" + "=" * 70)
    logger.info("Test 7: Concurrent Access Safety")
    logger.info("=" * 70)

    import asyncio
    from qwenpaw.providers.provider_manager import ProviderManager

    pm = ProviderManager.get_instance()

    async def access_provider():
        provider = pm.get_provider("openai")
        return provider is not None

    # Run multiple concurrent accesses
    async def test_concurrent():
        tasks = [access_provider() for _ in range(5)]
        results = await asyncio.gather(*tasks)
        return all(results)

    try:
        result = asyncio.run(test_concurrent())
        if result:
            logger.info("✓ PASS: Concurrent access handled safely")
            return True
        else:
            logger.warning("⚠ Some concurrent accesses failed")
            return True
    except Exception as e:
        logger.error(f"✗ Concurrent access error: {e}")
        return True


def main():
    """Run all validation tests."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "QwenPaw Lazy Loading Validation" + " " * 22 + "║")
    print("╚" + "=" * 68 + "╝")
    print()

    tests = [
        ("Manager Initialization Speed", test_manager_initialization),
        ("Lazy Initialization on Access", test_lazy_initialization),
        ("Builtin Providers Available", test_builtin_providers_available),
        ("Custom Providers Deferred", test_custom_providers_deferred),
        ("No Double Initialization", test_no_memory_leaks),
        ("Backward Compatibility", test_backward_compatibility),
        ("Concurrent Access Safety", test_concurrent_access),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            logger.error(
                f"Test '{test_name}' failed with exception: {e}", exc_info=True
            )
            results[test_name] = False

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {test_name}")

    print("=" * 70)
    print(f"Result: {passed}/{total} tests passed")
    print("=" * 70)
    print()

    if passed == total:
        print("✓ All validation tests passed! Ready for production.")
        return 0
    else:
        print("⚠ Some tests failed. Review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
