# Adaptive Tempo Sync Enhancement

## Problem
The current sync point generation sets `modified_tempo = original_tempo` for all sync points (line 365 in `beat_detector.py`). This works for the start but drift accumulates over time for recordings with tempo variation.

## Solution
Implement adaptive tempo sync that:
1. Calculates local BPM from detected beat intervals at each sync point
2. Places more sync points where tempo drifts significantly, sparse where stable
3. Generates a drift report showing detected vs expected tempo

## Implementation Steps

### Step 1: Create DriftAnalyzer Module
**File:** `src/guitarprotool/core/drift_analyzer.py` (NEW)

Create dataclasses:
```python
class DriftSeverity(Enum):
    STABLE = "stable"           # < 1% drift
    MINOR = "minor"             # 1-3% drift
    MODERATE = "moderate"       # 3-5% drift
    SIGNIFICANT = "significant" # 5-10% drift
    SEVERE = "severe"           # > 10% drift

@dataclass
class BarDriftInfo:
    bar: int
    expected_time: float
    actual_time: float
    local_tempo: float
    original_tempo: float
    drift_percent: float  # calculated
    severity: DriftSeverity  # calculated

@dataclass
class DriftReport:
    bar_drifts: List[BarDriftInfo]
    avg_drift_percent: float
    max_drift_percent: float
    max_drift_bar: int
    bars_with_significant_drift: List[int]
    tempo_stability_score: float  # 0.0-1.0
    recommended_sync_interval: int
```

Create `DriftAnalyzer` class:
- `__init__(beat_times, original_tempo, beats_per_bar, sample_rate)`
- `analyze(max_bars) -> DriftReport` - full drift analysis
- `get_drift_at_bar(bar) -> BarDriftInfo` - drift at specific bar
- `calculate_local_tempo_at_bar(bar) -> float` - local BPM using sliding window
- `generate_adaptive_sync_points(max_bars, base_interval) -> List[SyncPointData]`

Adaptive placement algorithm:
1. Always place sync point at bar 0
2. Place sync point if drift exceeds 2% threshold (min 2 bars apart)
3. Always place sync point at max 16 bar intervals
4. Set `modified_tempo` to detected local tempo at each sync point

### Step 2: Add Exceptions
**File:** `src/guitarprotool/utils/exceptions.py`

```python
class DriftAnalysisError(BeatDetectionError):
    """Raised when tempo drift analysis fails."""

class InsufficientBeatsError(DriftAnalysisError):
    """Raised when not enough beats for drift analysis."""
```

### Step 3: Integrate with BeatDetector
**File:** `src/guitarprotool/core/beat_detector.py`

Add `adaptive` parameter to `generate_sync_points()`:
```python
def generate_sync_points(
    self,
    beat_info: BeatInfo,
    original_tempo: float,
    ...
    adaptive: bool = True,  # NEW - enable adaptive tempo
) -> SyncResult:
```

When `adaptive=True`:
- Import and use `DriftAnalyzer`
- Call `generate_adaptive_sync_points()` instead of static generation
- Each sync point gets actual `modified_tempo` from local beat analysis

Refactor existing static logic to `_generate_static_sync_points()` for backward compatibility.

### Step 4: Update CLI with Drift Report
**File:** `src/guitarprotool/cli/main.py`

Add `display_drift_report()` function using rich:
```python
def display_drift_report(drift_report: DriftReport):
    # Summary panel with: bars analyzed, avg/max drift, stability score
    # Table of bars with significant drift (bar, local tempo, tab tempo, drift %)
```

Modify `run_pipeline()` (~line 447):
1. Create `DriftAnalyzer` and call `analyze()`
2. Pass `adaptive=True` to `generate_sync_points()`
3. Display drift report after sync point generation

### Step 5: Write Tests
**File:** `tests/test_drift_analyzer.py` (NEW)

Test cases:
- `test_analyze_stable_tempo` - perfectly stable tempo should have high stability score
- `test_analyze_drifting_tempo` - gradual tempo change should detect drift
- `test_adaptive_placement` - more sync points where drift is significant
- `test_local_tempo_calculation` - verify local BPM calculation accuracy
- `test_frame_offset_calculation` - verify frame positions are correct

Update `tests/test_beat_detector.py`:
- Test `adaptive=True` produces varying `modified_tempo` values
- Test `adaptive=False` maintains backward compatibility

## Files to Modify

| File | Change |
|------|--------|
| `src/guitarprotool/core/drift_analyzer.py` | NEW - core drift analysis |
| `src/guitarprotool/core/beat_detector.py` | Add `adaptive` param, integrate DriftAnalyzer |
| `src/guitarprotool/cli/main.py` | Display drift report |
| `src/guitarprotool/utils/exceptions.py` | Add drift exceptions |
| `tests/test_drift_analyzer.py` | NEW - test suite |
| `tests/test_beat_detector.py` | Update for adaptive param |

## Future Enhancement (Phase 2)
Note-transient matching for even more accurate alignment:
- Parse note positions from score.gpif XML
- Detect audio transients at those positions
- Match tab notes to audio transients
- Refine sync point positions based on actual note alignment

This is left as future work - the adaptive tempo sync should provide significant improvement first.
