"""Benchmark script for Action Verifier and Recovery Loop.

Measures:
1. End-to-end verification latency (median, mean, p95).
2. Action success confirmation rate.
3. False-success rejection rate (catching API false positives where outcome is absent).
4. Safety enforcement rate for non-idempotent operations.
5. Uncertainty rate on ambiguous or stale evidence.
"""

from pathlib import Path
import sys
import time
from typing import Any, Dict, List
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from action_expectations import ActionExpectation, ActionIntent, ActionRiskLevel
from action_verifier import ActionVerifier, VerificationStatus
from action_recovery import ActionRecoveryDecider, RecoveryStrategy


def run_benchmark(iterations: int = 50, verbose: bool = True) -> Dict[str, Any]:
    print(f"=== Action Verification & Recovery Benchmark ({iterations} iterations per scenario) ===")
    verifier = ActionVerifier()
    recovery = ActionRecoveryDecider(max_safe_retries=1)

    scenarios = [
        # Scenario 1: Legitimate window title change (Expected success)
        {
            "name": "legitimate_window_change",
            "intent": ActionIntent(
                action_type="focus_window",
                target_query="Settings",
                expectation=ActionExpectation(expected_window_title="Settings"),
            ),
            "pre": {"observation_id": "snap_1", "active_window": "Browser"},
            "dispatch": {"success": True},
            "post": {"observation_id": "snap_2", "active_window": "Settings - System"},
            "expected_status": VerificationStatus.CONFIRMED,
        },
        # Scenario 2: False positive driver dispatch (API succeeded, but UI did not react)
        {
            "name": "false_positive_rejection",
            "intent": ActionIntent(
                action_type="click_element",
                target_id=42,
                expectation=ActionExpectation(expected_window_title="Settings"),
            ),
            "pre": {"observation_id": "snap_1", "active_window": "Browser"},
            "dispatch": {"success": True},  # Driver says click was sent
            "post": {"observation_id": "snap_2", "active_window": "Browser"},  # But window didn't open
            "expected_status": VerificationStatus.FAILED,
        },
        # Scenario 3: Legitimate OCR text appearance
        {
            "name": "ocr_text_appearance",
            "intent": ActionIntent(
                action_type="type_text",
                parameters={"text": "search query"},
                expectation=ActionExpectation(expected_text="Results found"),
            ),
            "pre": {"observation_id": "snap_1"},
            "dispatch": {"success": True},
            "post": {"observation_id": "snap_2", "text": "Results found: 42 matching items"},
            "expected_status": VerificationStatus.CONFIRMED,
        },
        # Scenario 4: Stale observation detection
        {
            "name": "stale_observation_detection",
            "intent": ActionIntent(
                action_type="click_element",
                target_id=10,
                expectation=ActionExpectation(expected_text="Updated"),
            ),
            "pre": {"observation_id": "identical_snapshot_1"},
            "dispatch": {"success": True},
            "post": {"observation_id": "identical_snapshot_1", "text": "Updated"},
            "expected_status": VerificationStatus.UNCERTAIN,
        },
        # Scenario 5: Non-idempotent action failure (Safety abort)
        {
            "name": "non_idempotent_safety_abort",
            "intent": ActionIntent(
                action_type="click_element",
                target_query="Submit Payment",
                risk_level=ActionRiskLevel.NON_IDEMPOTENT,
                expectation=ActionExpectation(expected_text="Payment Confirmed"),
            ),
            "pre": {"observation_id": "snap_1"},
            "dispatch": {"success": True},
            "post": {"observation_id": "snap_2", "text": "Gateway Timeout"},
            "expected_status": VerificationStatus.FAILED,
        },
    ]

    latencies_ms: List[float] = []
    confirmed_count = 0
    rejected_false_positives = 0
    uncertain_count = 0
    total_evals = 0
    safety_aborts = 0

    for scenario in scenarios:
        scenario_latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            evidence = verifier.verify(
                scenario["intent"],
                scenario["pre"],
                scenario["dispatch"],
                scenario["post"],
            )
            rec = recovery.decide(scenario["intent"], evidence)
            t1 = time.perf_counter()

            lat_ms = (t1 - t0) * 1000.0
            scenario_latencies.append(lat_ms)
            latencies_ms.append(lat_ms)
            total_evals += 1

            if evidence.status == VerificationStatus.CONFIRMED:
                confirmed_count += 1
            elif evidence.status == VerificationStatus.UNCERTAIN:
                uncertain_count += 1

            if scenario["name"] == "false_positive_rejection" and evidence.status == VerificationStatus.FAILED:
                rejected_false_positives += 1

            if scenario["name"] == "non_idempotent_safety_abort" and rec.strategy == RecoveryStrategy.ABORT_FOR_SAFETY:
                safety_aborts += 1

        if verbose:
            print(
                f"  [{scenario['name']:<28}] Mean: {np.mean(scenario_latencies):.3f}ms | "
                f"P95: {np.percentile(scenario_latencies, 95):.3f}ms"
            )

    arr = np.array(latencies_ms)
    results = {
        "total_evaluations": total_evals,
        "latency_median_ms": round(float(np.median(arr)), 3),
        "latency_mean_ms": round(float(np.mean(arr)), 3),
        "latency_p95_ms": round(float(np.percentile(arr, 95)), 3),
        "action_confirmed_rate": round(confirmed_count / total_evals * 100.0, 1),
        "false_positive_rejection_rate": round(rejected_false_positives / iterations * 100.0, 1),
        "uncertainty_rate": round(uncertain_count / total_evals * 100.0, 1),
        "safety_abort_compliance_rate": round(safety_aborts / iterations * 100.0, 1),
    }

    if verbose:
        print("-" * 60)
        print(f"Total Evaluations:                {results['total_evaluations']}")
        print(f"Median Latency:                   {results['latency_median_ms']} ms")
        print(f"P95 Latency:                      {results['latency_p95_ms']} ms")
        print(f"False-Positive Rejection Rate:    {results['false_positive_rejection_rate']}%")
        print(f"Safety Abort Compliance Rate:     {results['safety_abort_compliance_rate']}%")
        print(f"Action Confirmation Rate:         {results['action_confirmed_rate']}%")
        print(f"Uncertainty Rate:                 {results['uncertainty_rate']}%")
        print("=" * 60)

    return results


if __name__ == "__main__":
    run_benchmark(iterations=100, verbose=True)
