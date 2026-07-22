"""Verify the shared-ModelInfo bug between China and International providers.

The hypothesis: PROVIDER_ALIYUN_TOKENPLAN and PROVIDER_ALIYUN_TOKENPLAN_INTL
share the *same* ModelInfo object instances (via ALIYUN_TOKENPLAN_MODELS).
When _init_from_storage restores China-region overrides in-place, the
International provider sees the mutated values too.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from qwenpaw.providers.provider_manager import (
    PROVIDER_ALIYUN_TOKENPLAN,
    PROVIDER_ALIYUN_TOKENPLAN_INTL,
    PROVIDER_ALIYUN_CODINGPLAN,
    PROVIDER_ALIYUN_CODINGPLAN_INTL,
    ALIYUN_TOKENPLAN_MODELS,
    ALIYUN_CODINGPLAN_MODELS,
)


def check_identity(label, provider_cn, provider_intl):
    """Check whether two providers share the same ModelInfo instances."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    # 1. Check if .models is the exact same list object
    same_list = provider_cn.models is provider_intl.models
    print(f"  provider_cn.models is provider_intl.models: {same_list}")

    # 2. Check per-model identity
    cn_by_id = {m.id: m for m in provider_cn.models}
    intl_by_id = {m.id: m for m in provider_intl.models}

    shared_ids = set(cn_by_id) & set(intl_by_id)
    shared_objects = []
    for model_id in sorted(shared_ids):
        is_same = cn_by_id[model_id] is intl_by_id[model_id]
        shared_objects.append((model_id, is_same))
        print(f"    {model_id}: same object = {is_same}  "
              f"(cn id={id(cn_by_id[model_id])}, intl id={id(intl_by_id[model_id])})")

    # 3. Simulate the bug: mutate China side, check International side
    print(f"\n  --- Simulating _restore_builtin_model_config mutation ---")
    for model_id, is_same in shared_objects:
        if is_same:
            cn_model = cn_by_id[model_id]
            intl_model = intl_by_id[model_id]

            # Record original value
            original_max_tokens = intl_model.max_tokens

            # Simulate China region saving max_tokens=4096
            cn_model.max_tokens = 4096

            # Check if International side is affected
            leaked = intl_model.max_tokens == 4096
            print(f"    {model_id}: set CN max_tokens=4096 -> "
                  f"INTL max_tokens={intl_model.max_tokens} "
                  f"(leaked={leaked})")

            # Restore
            cn_model.max_tokens = original_max_tokens

    # Summary
    any_shared = any(is_same for _, is_same in shared_objects)
    return any_shared


def main():
    print("=" * 60)
    print("  Shared ModelInfo Bug Verification")
    print("=" * 60)

    results = {}

    results["TokenPlan"] = check_identity(
        "ALIYUN_TOKENPLAN vs ALIYUN_TOKENPLAN_INTL",
        PROVIDER_ALIYUN_TOKENPLAN,
        PROVIDER_ALIYUN_TOKENPLAN_INTL,
    )

    results["CodingPlan"] = check_identity(
        "ALIYUN_CODINGPLAN vs ALIYUN_CODINGPLAN_INTL",
        PROVIDER_ALIYUN_CODINGPLAN,
        PROVIDER_ALIYUN_CODINGPLAN_INTL,
    )

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    bug_confirmed = False
    for pair_name, has_shared in results.items():
        status = "BUG CONFIRMED - shared ModelInfo objects!" if has_shared else "OK - no sharing"
        print(f"  {pair_name}: {status}")
        if has_shared:
            bug_confirmed = True

    if bug_confirmed:
        print("\n  *** BUG EXISTS: China and International providers share")
        print("      the same ModelInfo instances. In-place mutation in")
        print("      _restore_builtin_model_config will leak overrides. ***")
        sys.exit(1)
    else:
        print("\n  No bug detected.")
        sys.exit(0)


if __name__ == "__main__":
    main()
