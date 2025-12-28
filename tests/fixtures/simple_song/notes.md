# Simple Song Test Case

**Song:** Nirvana - In Bloom

## Test Characteristics

- **Intro type:** Music starts on the first beat
- **Tempo:** Consistent throughout
- **Bass pattern:** Clear, rhythmic bass line
- **Expected difficulty:** Easy - high accuracy expected

## What This Tests

1. Basic beat detection accuracy
2. Sync point generation at regular intervals
3. Standard pipeline workflow without bass isolation complexity

## Expected Results

- Sync points should align closely with reference
- Minimal tempo drift corrections needed
- Frame offsets should be within ~100ms of reference

## Running This Test

```bash
guitarprotool -i tests/fixtures/simple_song/input.gp \
  -y "$(cat tests/fixtures/simple_song/youtube_url.txt)" \
  -o /tmp/simple_output.gp \
  --compare tests/fixtures/simple_song/reference.gp
```

## Reference File Notes

The reference file was created by:
1. Running the tool to generate initial sync points
2. Opening in Guitar Pro 8 and playing along
3. Adjusting sync points where audio drifted from tab
4. Saving the corrected file as reference.gp
