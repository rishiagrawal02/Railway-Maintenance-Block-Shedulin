# Selector Held-Out Evaluation Report

**Date**: 2026-10-25 20:37:48 UTC  
**Git Hash**: `17bc7996db0e1865132fdcbd15623613e1d64255`  
**Threshold**: 0.7150  
**Alpha**: `[0.2, 0.2, 0.2, 0.2, 0.2]`  

## Accuracy vs Majority Baseline

| Metric | Value |
|---|---|
| Evaluation Samples | 20 |
| Class 1 (Exact Affordable) | 20 |
| Class 0 (Exact Costly) | 0 |
| **Selector Accuracy** | **100.00%** |
| **Majority-Class Baseline** | **100.00%** |

## Summary
The calibrated threshold separates instances where exact ILP solving is feasible within the
deterministic budget from instances that require heuristic routing.
