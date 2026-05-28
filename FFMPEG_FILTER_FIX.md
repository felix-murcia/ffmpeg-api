# FFmpeg Filter Fix: agate Threshold Conversion

## Problem
Audio post-processing was failing with:
```
Error reinitializing filters!
Failed to inject frame into filter network: Filter not found
Conversion failed!
```

## Root Cause
Three issues were preventing the breathing artifact removal from working:

1. **Non-existent filter**: Used `gate=` but ffmpeg compiled without it
2. **Wrong filter name**: The correct filter is `agate` (audio gate filter)
3. **Incorrect threshold format**: 
   - `agate` filter expects `threshold` in range [0, 1]
   - We were passing -40 dB directly, which is outside valid range
   - Need to convert dB to linear scale: `10^(dB/20)`

## Solution
Updated `audio_post_processor.py` to:

```python
def _remove_breathing_artifacts(self, ...):
    # Convert threshold from dB to linear scale (0-1)
    # agate filter expects threshold in 0-1 range: 10^(dB/20)
    threshold_linear = 10 ** (noise_gate_threshold / 20)
    # Clamp to valid range [0.001, 1.0]
    threshold_linear = max(0.001, min(1.0, threshold_linear))
    
    filters_with_gate = (
        f"highpass=f=80,"
        f"agate=threshold={threshold_linear:.4f}:ratio=2:attack=5:release=50"
    )
```

### Parameter Changes
| Parameter | Before | After | Reason |
|-----------|--------|-------|--------|
| Filter | `gate=` | `agate=` | Only agate exists in ffmpeg |
| threshold | `-40.0dB` | `0.0100` | Converted to linear scale (10^(-40/20)) |
| ratio | `10` | `2` | agate default ratio |
| attack | `0.005` | `5` | milliseconds (was too fast) |
| release | `0.1` | `50` | milliseconds (was too fast) |

### Conversion Formula
```
For threshold -40 dB:
threshold_linear = 10^(-40/20) = 10^(-2) = 0.01
```

## Verification
✅ Endpoint `/audio/post-process` now completes successfully
✅ No filter errors in logs
✅ Output audio generated: 768 KB WAV file
✅ All processing steps (normalize, breathing removal, plosive stabilization, compression) work

## Files Modified
- `src/modules/audio_helper/audio_post_processor.py` (lines 172-190)

## Testing
```bash
# Create test audio
ffmpeg -f lavfi -i sine=f=440:d=2 -q:a 9 /tmp/test.wav

# Call endpoint
curl -X POST http://localhost:8082/audio/post-process \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/tmp/test.wav",
    "normalize": true,
    "remove_breathing": true,
    "stabilize_plosives": true,
    "noise_gate_threshold": -40.0
  }' \
  -o /tmp/result.wav

# Result: Status 200, valid WAV file
```

## References
- ffmpeg agate filter: https://ffmpeg.org/ffmpeg-filters.html#agate_002c-sidechaingate
- dB to linear conversion: `10^(dB/20)`
