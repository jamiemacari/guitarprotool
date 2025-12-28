# Complex Intro Test Case

**Song:** Air - La Femme d'Argent

## Test Characteristics

- **Intro type:** Ambient/instrumental intro before bass enters
- **Tempo:** May have slight variations
- **Bass pattern:** Enters after several bars of ambient intro
- **Expected difficulty:** Moderate - tests bass isolation feature

## What This Tests

1. Bass isolation for finding where bass starts
2. Tab start bar detection (skipping intro bars)
3. Alignment of audio to first note bar
4. Handling of complex/ambient audio

## Expected Results

- Should correctly identify where bass enters
- Sync points should align with bass notes, not ambient intro
- Reference may have fewer sync points (manually added only where needed)
- Extra sync points in generated file are acceptable

## Running This Test

```bash
guitarprotool -i tests/fixtures/complex_intro/input.gp \
  -y "$(cat tests/fixtures/complex_intro/youtube_url.txt)" \
  -o /tmp/complex_output.gp \
  --compare tests/fixtures/complex_intro/reference.gp
```

## Reference File Notes

The reference file was created by:
1. Running the tool with bass isolation enabled
2. Opening in Guitar Pro 8 and playing along
3. Verifying that bass notes align with tab
4. Adding sync points at bars where drift was noticeable
5. Saving the corrected file as reference.gp

## Notes on Bass Isolation

This test case benefits significantly from bass isolation:
- Without bass isolation: may detect beats from drums/other instruments in intro
- With bass isolation: correctly finds where bass actually starts

If bass isolation is not installed, the tool will fall back to full-mix beat detection,
which may produce different (but still functional) sync points.
