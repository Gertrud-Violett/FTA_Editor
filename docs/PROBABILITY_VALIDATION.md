# FTA Editor Probability Calculation Validation

## Overview
This document validates and documents the probability calculation logic in the FTA Editor, specifically focusing on how AND/OR gates and links are handled.

## Validation Status
✅ **All tests passed** - 13/13 test cases successful

## Probability Calculation Logic

### 1. Basic Calculation Flow

The `recalculate_probabilities()` method traverses the fault tree and calculates probabilities for each node using memoization and cycle detection.

**Key features:**
- **Memoization**: Prevents redundant calculations by caching results
- **Cycle detection**: Uses a `visiting` set to detect and handle circular references
- **Bottom-up calculation**: Calculates child probabilities before parent probabilities

### 2. Logic Gates for Children

When a node has children, the gate type determines how child probabilities are combined:

#### AND Gate
**Formula**: `∏(child_probabilities)`

**Example:**
```
Node with AND gate
Children: [0.5, 0.4]
Result: 0.5 × 0.4 = 0.2
```

**Interpretation**: All child events must occur.

**Note**: The parent node's base probability is **not** included in the calculation when the node has children and a logic gate. The calculated probability is determined solely by the children and the gate type.

**Code location**: `FTA_Editor_core.py`, lines ~175-176
```python
if gate == "AND":
    base = round(self._product(child_probs), 6)
```

#### OR Gate
**Formula**: `1 - ∏(1 - child_probability)`

**Example:**
```
Node with OR gate
Children: [0.5, 0.4]
Result: 1 - (1-0.5)×(1-0.4) = 1 - 0.5×0.6 = 1 - 0.3 = 0.7
```

**Interpretation**: At least one child event occurs (union of independent events).

**Code location**: `FTA_Editor.py`, lines 463-464
```python
else:  # OR gate
    base = round(1 - self._product([1 - p for p in child_probs]), 6)
```

### 3. Links Between Nodes

Nodes can have links to other nodes in the tree, creating dependencies beyond the parent-child hierarchy.

#### AND Links
**Formula**: `current_probability × ∏(AND_linked_probabilities)`

**Example:**
```
Node with prob = 0.8
AND link to node with prob = 0.6
Result: 0.8 × 0.6 = 0.48
```

**Interpretation**: The current event AND the linked event must both occur.

**Code location**: `FTA_Editor.py`, lines 482-483
```python
if and_probs:
    base = round(base * self._product(and_probs), 6)
```

#### OR Links
**Formula**: `1 - ∏(1 - probability)` for [current_probability, OR_linked_probabilities]

**Example:**
```
Node with prob = 0.5
OR link to node with prob = 0.3
Result: 1 - (1-0.5)×(1-0.3) = 1 - 0.5×0.7 = 0.65
```

**Interpretation**: Either the current event OR the linked event occurs (union).

**Code location**: `FTA_Editor.py`, lines 484-486
```python
if or_probs:
    vals = [base] + or_probs
    base = round(1 - self._product([1 - p for p in vals]), 6)
```

### 4. Processing Order

The calculation follows this specific order:

1. **Calculate children probabilities** (recursive, depth-first)
2. **Apply logic gate** (AND or OR) to combine children with base probability
3. **Apply AND links** (multiply with linked node probabilities)
4. **Apply OR links** (union with linked node probabilities)

**This order matters!** AND links are applied before OR links.

**Example with mixed links:**
```
Node: base_prob = 0.5
AND link to node with prob = 0.8
OR link to node with prob = 0.4

Step 1: Apply AND link: 0.5 × 0.8 = 0.4
Step 2: Apply OR link: 1 - (1-0.4)×(1-0.4) = 1 - 0.36 = 0.64
```

### 5. Edge Cases

#### Zero Probabilities
- Zero probabilities propagate through AND gates
- Zero probabilities have minimal effect on OR gates
- **Tested**: ✅ Test case `test_zero_probability_leaf`

#### Circular References
- Detected via the `visiting` set
- When detected, uses the node's base probability
- Prevents infinite loops
- **Tested**: ✅ Test case `test_circular_reference_protection`

#### Leaf Nodes (No Children)
- Use their base probability directly
- **Tested**: ✅ Test case `test_leaf_node_probability`

## Test Coverage

### Test Cases Implemented

1. **`test_leaf_node_probability`** - Validates leaf nodes use base probability
2. **`test_and_gate_with_two_children`** - Validates AND gate with 2 children
3. **`test_or_gate_with_two_children`** - Validates OR gate with 2 children
4. **`test_and_gate_with_three_children`** - Validates AND gate with 3 children
5. **`test_or_gate_with_three_children`** - Validates OR gate with 3 children
6. **`test_and_link_simple`** - Validates AND links between nodes
7. **`test_or_link_simple`** - Validates OR links between nodes
8. **`test_mixed_and_or_links`** - Validates nodes with both AND and OR links
9. **`test_zero_probability_leaf`** - Validates zero probability handling
10. **`test_nested_and_gates`** - Validates nested AND gates
11. **`test_nested_or_gates`** - Validates nested OR gates
12. **`test_circular_reference_protection`** - Validates circular reference handling
13. **`test_sample_event_1_1_1`** - Validates against actual sample data

### Running Tests

```bash
cd FTA_Editor
python test_probability_calculation.py
```

Expected output:
```
Ran 13 tests in 0.001s
OK
```

## Validation Results

### AND Gate Validation ✅
- Two children: **PASS**
- Three children: **PASS**
- Nested gates: **PASS**
- Formula confirmed: `∏(child_probs)` (parent base probability not included)

### OR Gate Validation ✅
- Two children: **PASS**
- Three children: **PASS**
- Nested gates: **PASS**
- Formula confirmed: `1 - ∏(1 - child_prob)`

### AND Links Validation ✅
- Simple AND link: **PASS**
- Formula confirmed: `current_prob × ∏(AND_linked_probs)`

### OR Links Validation ✅
- Simple OR link: **PASS**
- Formula confirmed: `1 - ∏(1 - prob)` for current + OR-linked probs

### Mixed Scenarios Validation ✅
- AND and OR links together: **PASS**
- Processing order confirmed: AND links first, then OR links

### Edge Cases Validation ✅
- Zero probabilities: **PASS**
- Circular references: **PASS**
- Leaf nodes: **PASS**

## Mathematical Correctness

The implementation follows standard probability theory:

### AND (Intersection of Independent Events)
For independent events A and B:
```
P(A ∩ B) = P(A) × P(B)
```

### OR (Union of Independent Events)
For independent events A and B:
```
P(A ∪ B) = 1 - P(¬A ∩ ¬B) = 1 - (1-P(A))×(1-P(B))
```

This is equivalent to the inclusion-exclusion principle:
```
P(A ∪ B) = P(A) + P(B) - P(A ∩ B)
```

## Sample Data Verification

The test `test_sample_event_1_1_1` validates the calculation from `sampleFTA.json`:

**Event1.1.1** (id: root_0_0_0):
- Base probability: 0.5
- AND link to Ev1.3 (prob: 0.8)
- OR link to Ev2.2 (prob: 0.0)

**Expected calculation:**
1. Apply AND link: 0.5 × 0.8 = 0.4
2. Apply OR link: 1 - (1-0.4)×(1-0.0) = 0.4

**Result:** ✅ Matches expected value of 0.4

## Conclusion

The probability calculation function in the FTA Editor has been thoroughly validated:

✅ **AND/OR gate logic is mathematically correct**
✅ **Link handling (AND/OR) is properly implemented**
✅ **Processing order is correct and consistent**
✅ **Edge cases are handled appropriately**
✅ **13/13 automated tests pass**

The implementation correctly follows probability theory for combining independent events and properly handles the fault tree analysis requirements.

## Future Considerations

While the current implementation is correct, potential enhancements could include:

1. **Dependent Events**: Currently assumes all events are independent
2. **Conditional Probabilities**: Support for conditional probability relationships
3. **Time-dependent Failures**: Support for failure rates over time
4. **Uncertainty Quantification**: Confidence intervals for calculated probabilities

These are outside the current scope but could be valuable additions for advanced FTA scenarios.

## References

- Test file: `test_probability_calculation.py`
- Implementation: `FTA_Editor.py`, method `recalculate_probabilities()` (lines 438-495)
- Sample data: `sampleFTA.json`
