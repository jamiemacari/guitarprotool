# Bass Transcription Roadmap

## Overview

This document outlines the research and implementation plan for adding automated bass tab transcription capabilities to the Guitar Pro Audio Injection Tool. The goal is to move beyond simple beat detection to full rhythm recognition and eventually automated bass tab writing with proper music notation.

**Status**: Research Complete, Ready for Phase 1 Implementation
**Target Accuracy**: 80%+ on simple root-note bass lines
**Timeline**: 4 months to fully integrated feature
**Last Updated**: 2025-12-27

---

## Executive Summary

### Current State
- ✅ Beat detection using librosa (BPM and beat positions)
- ✅ Bass isolation using Demucs v4 (isolates bass from full mix)
- ✅ Adaptive tempo sync (handles tempo drift)
- ❌ No rhythm pattern recognition (syncopation, subdivisions)
- ❌ No pitch detection (can't identify which notes are played)
- ❌ No transcription capabilities (can't generate tab notation)

### Proposed Solution
Build an incremental transcription pipeline using state-of-the-art Music Information Retrieval (MIR) libraries:

1. **madmom** - Better onset/beat detection (10-15% improvement over librosa)
2. **CREPE** - Pitch detection for monophonic bass (95-98% accuracy)
3. **music21** - Rhythm quantization (convert onsets to standard notation)
4. **mir_eval** - Objective accuracy measurement against ground truth
5. **Guitar Pro XML integration** - Inject transcribed tabs directly into .gp files

### Expected Outcomes
- **Clean recordings**: 65-80% fully correct notes (pitch + rhythm)
- **Live/noisy recordings**: 50-65% fully correct notes
- **User requirement**: 80%+ accuracy on simple root-note bass lines
- **Manual refinement**: < 5 minutes per song

---

## User Requirements

Based on user consultation (2025-12-27):

- **Priority**: Incremental improvements (start with madmom for beat detection)
- **Complexity**: Simple root notes initially (maximize accuracy)
- **Test Data**: Existing Guitar Pro bass tabs available for ground truth validation
- **Accuracy Goal**: 80%+ required to be useful

---

## Market Research: MIR Tools

### 1. Pitch Detection (Which Notes Are Playing)

#### CREPE (Recommended for Monophonic Bass)
- **Type**: Deep CNN pitch tracker (ICASSP 2018)
- **Accuracy**: 95-98% on clean monophonic recordings
- **Output**: Timestamp, frequency (Hz), confidence per 10ms frame
- **Install**: `pip install crepe`
- **Repository**: [github.com/marl/crepe](https://github.com/marl/crepe)
- **Use Case**: Perfect for isolated bass tracks (monophonic instrument)
- **Why**: State-of-the-art monophonic pitch detection, operates directly on waveform

#### Basic Pitch (Alternative for Polyphonic Bass)
- **Type**: Lightweight CNN (Spotify, ICASSP 2022)
- **Accuracy**: 85-90% (generalized across instruments)
- **Output**: Direct MIDI file with pitch bend
- **Install**: `pip install basic-pitch`
- **Repository**: [github.com/spotify/basic-pitch](https://github.com/spotify/basic-pitch)
- **Use Case**: Bass with chords/double stops
- **Strategy**: Keep as fallback for complex passages

### 2. Rhythm Pattern Detection (When Notes Start/Stop)

#### madmom (Highly Recommended)
- **Type**: State-of-the-art onset/beat detection (ISMIR 2010-2016)
- **Accuracy**: 90-95% F-measure (vs 80-85% for librosa)
- **Features**:
  - Advanced onset detection using LSTM/RNN
  - Beat, downbeat, and meter tracking
  - Syncopation and subdivision detection
- **Install**: `pip install madmom`
- **Repository**: [github.com/CPJKU/madmom](https://github.com/CPJKU/madmom)
- **Immediate Win**: Replace `librosa.onset.onset_detect()` with `madmom.features.onsets`
- **Expected Improvement**: 10-15% better onset precision

### 3. Rhythm Quantization (Converting to Standard Notation)

#### music21 (MIT's Computational Musicology Toolkit)
- **Type**: Comprehensive music analysis library
- **Features**:
  - Rhythm quantization via `Stream.quantize()`
  - MIDI/MusicXML import/export
  - Note duration modeling
  - Custom quantization grids
- **Install**: `pip install music21`
- **Website**: [web.mit.edu/music21](https://web.mit.edu/music21)
- **Use Case**: Convert messy onset times → clean notation (quarter notes, eighths, etc.)
- **Note**: Large dependency (~500MB with corpora)

### 4. Accuracy Evaluation

#### mir_eval (Essential for Validation)
- **Type**: Standardized MIR evaluation metrics (ISMIR 2014)
- **Features**:
  - `mir_eval.beat.evaluate()` - Beat accuracy
  - `mir_eval.onset.evaluate()` - Onset precision/recall
  - `mir_eval.transcription.evaluate()` - Note-level F-measure
  - `mir_eval.melody.evaluate()` - Pitch accuracy
- **Install**: `pip install mir_eval`
- **Repository**: [github.com/mir-evaluation/mir_eval](https://github.com/mir-evaluation/mir_eval)
- **Use Case**: Objectively measure transcription accuracy against ground truth tabs

---

## Implementation Phases

### Phase 1: Improve Beat Detection (Week 1)
**Goal**: 10-15% better onset detection with minimal code changes

**Tasks**:
1. Add `madmom` to `[transcription]` optional dependency group
2. Modify `beat_detector.py`:
   - Add `madmom.features.onsets.OnsetDetector` as alternative to librosa
   - Keep librosa as fallback (optional dependency pattern)
   - Add parameter: `detector='madmom'` or `detector='librosa'`
3. Add `mir_eval` for evaluation metrics
4. Create baseline: Test current librosa against ground truth tabs
5. Test madmom: Measure improvement using `mir_eval.onset.evaluate()`

**Success Criteria**:
- Onset detection F-measure improves by ≥10%
- No regression in existing audio injection workflow
- User validates on 3-5 test songs

**Deliverables**:
- Enhanced `BeatDetector` class with madmom support
- Baseline accuracy report (librosa vs madmom)
- Go/No-Go decision for Phase 2

---

### Phase 2: Add Pitch Detection (Week 2-3)
**Goal**: Detect which bass notes are being played with 95%+ accuracy

**Tasks**:
1. Create `src/guitarprotool/core/pitch_detector.py`:
   - `PitchDetector` class using CREPE
   - Methods: `analyze(audio_path)`, `get_midi_notes(min_confidence=0.8)`
   - Dataclass: `PitchInfo(times, frequencies, confidences, midi_notes)`
2. Add CREPE to `[transcription]` dependencies
3. Integrate with existing pipeline:
   - Use isolated bass WAV from `BassIsolator`
   - Filter by confidence threshold (≥0.8)
   - Map frequencies → MIDI notes (bass range E1-B3)
4. Test against ground truth using `mir_eval.melody.evaluate()`
5. Create visualization: Plot detected pitches vs actual tab

**Success Criteria**:
- Pitch accuracy ≥95% on simple root-note bass lines
- Low false positive rate (confidence filtering effective)
- Processing time < 2x audio duration

**Deliverables**:
- `PitchDetector` class with full test coverage
- Pitch accuracy report on 5-10 test songs
- Documented edge cases (slides, harmonics, noise)

---

### Phase 3: Rhythm Quantization (Month 2)
**Goal**: Convert detected onsets → standard music notation durations

**Tasks**:
1. Create `src/guitarprotool/core/rhythm_quantizer.py`:
   - `RhythmQuantizer` class using music21
   - Methods: `quantize(onset_times, bpm, time_signature='4/4')`, `get_durations()`
   - Handle: Quarter notes, eighths, sixteenths, dotted notes
   - Skip triplets (defer to later phase)
2. Add `music21` to `[transcription]` dependencies
3. Integrate with `BeatDetector`:
   - Use detected BPM and bar boundaries
   - Snap onset times to nearest grid position
   - Calculate note durations (time until next onset or bar end)
4. Test quantization accuracy:
   - Compare vs ground truth tabs
   - Identify problematic patterns (syncopation, very short notes)

**Success Criteria**:
- Rhythm accuracy ≥80% on simple patterns (quarters and eighths)
- Quantization preserves musicality
- User validates on 5-10 test songs

**Deliverables**:
- `RhythmQuantizer` class with test coverage
- Rhythm accuracy report
- List of edge cases for future handling

---

### Phase 4: MIDI Generation (Month 2-3)
**Goal**: Combine pitch + rhythm → MIDI file for validation

**Tasks**:
1. Create `src/guitarprotool/core/transcription_engine.py`:
   - `TranscriptionEngine` class
   - Methods: `generate_midi(pitch_info, rhythm_info, output_path)`
   - Combine pitch (CREPE) + duration (RhythmQuantizer)
   - Handle overlapping notes, sustained notes, note merging
2. Add `mido` to dependencies (lightweight MIDI library)
3. Validate MIDI output:
   - Bass note range check (E1-B3 typical, E1-C4 extended)
   - Tempo matches detected BPM
   - Duration totals match song length
4. Create MIDI comparison tool:
   - Load ground truth tab as MIDI
   - Compare generated vs ground truth using `mir_eval.transcription.evaluate()`
5. Human validation: User listens to MIDI playback

**Success Criteria**:
- Overall transcription accuracy ≥80% (combined pitch + rhythm)
- MIDI sounds recognizable as original bass line
- Pipeline completes without errors

**Deliverables**:
- `TranscriptionEngine` class with test coverage
- MIDI files for 10+ test songs
- Comprehensive accuracy report
- Identified failure modes and edge cases

---

### Phase 5: Guitar Pro Tab Injection (Month 3-4)
**Goal**: Inject auto-generated bass tab into Guitar Pro XML

**Tasks**:
1. Research GP8 XML structure for note/rhythm elements:
   - Analyze existing bass tabs to understand schema
   - Document: `<Note>`, `<Rhythm>`, `<Beat>`, `<Fret>` elements
   - Add findings to `docs/GP8_FORMAT.md`
2. Extend `XMLModifier` class:
   - Add method: `inject_bass_tab(transcription, track_index)`
   - Generate XML for each note (pitch, duration, fret position)
   - Handle rhythm notation (quarter, eighth, sixteenth flags)
   - Map MIDI notes → bass fret positions
3. Fret position optimization:
   - Simple heuristic: Minimize position changes
   - Prefer open strings for E, A, D, G notes
   - Higher frets for chromatic passages
4. Test on sample .gp file:
   - Load empty bass tab
   - Inject transcription
   - Verify file opens in Guitar Pro 8
   - Validate tab is playable and readable
5. End-to-end pipeline test:
   - YouTube URL → Audio → Isolation → Transcription → GP file
   - Measure accuracy vs manually created tabs

**Success Criteria**:
- Generated .gp files open correctly in GP8
- Bass tab is readable and makes musical sense
- Fret positions are reasonable (minimal jumping)
- Overall workflow accuracy ≥80%

**Deliverables**:
- Enhanced `XMLModifier` with tab injection
- Documentation of GP8 note/rhythm XML schema
- 5-10 test .gp files with auto-generated bass tabs
- End-to-end accuracy report

---

### Phase 6: CLI Integration & User Testing (Month 4)
**Goal**: Make transcription feature accessible via CLI

**Tasks**:
1. Modify `cli/main.py`:
   - Add menu option: "Transcribe bass tab from audio"
   - Workflow: Audio source → Isolation → Transcription → MIDI/GP output
   - Progress feedback for each phase (Rich progress bars)
   - Display accuracy metrics if ground truth provided
2. Add confidence visualization:
   - Show note-level confidence scores
   - Flag low-confidence notes for manual review
   - Generate confidence report (PDF/HTML)
3. Error handling:
   - Graceful fallback if pitch detection fails
   - Warning for tempo/key changes
   - User override for BPM, time signature
4. Documentation:
   - Update README with transcription examples
   - Add troubleshooting guide
   - Document accuracy expectations and limitations
5. User acceptance testing:
   - User tests on 20+ songs of varying complexity
   - Collect feedback on accuracy, usability, edge cases
   - Iterate on problematic areas

**Success Criteria**:
- User can transcribe bass tabs in < 5 commands
- Accuracy meets 80%+ target on simple root-note songs
- User satisfied with workflow and output quality
- Clear path identified for handling failures

**Deliverables**:
- Fully integrated CLI transcription feature
- User documentation and examples
- User testing report with accuracy statistics
- Prioritized backlog for improvements

---

## Proposed Architecture

### Full Pipeline Flow
```
YouTube URL → AudioProcessor → MP3 192kbps
              ↓
MP3 → BassIsolator (Demucs) → Isolated Bass WAV
              ↓
Bass WAV → madmom.features.onsets → Note Onset Times
         → madmom.features.beats → Beat Grid + Downbeats
              ↓
Onset Times → music21.Stream.quantize() → Note Durations
              ↓
Bass WAV → CREPE → (time, frequency, confidence)
         → Filter by confidence → MIDI notes
              ↓
Merge rhythm + pitch → TranscriptionEngine → MIDI file
              ↓
MIDI → Parse notes/durations → Generate GP8 XML
     → XMLModifier.inject_bass_tab() → .gp file
```

### New Modules

**`pitch_detector.py`**
- Class: `PitchDetector`
- Methods: `analyze(audio_path)`, `get_midi_notes(min_confidence)`
- Dataclass: `PitchInfo(times, frequencies, confidences, midi_notes)`

**`rhythm_quantizer.py`**
- Class: `RhythmQuantizer`
- Methods: `quantize(onset_times, bpm, time_signature)`, `get_durations()`
- Dataclass: `QuantizedRhythm(onset_times, durations, subdivisions)`

**`transcription_engine.py`**
- Class: `TranscriptionEngine`
- Methods: `generate_midi(pitch_info, rhythm_info)`, `validate_bass_range()`
- Dataclass: `Transcription(notes, durations, pitches, midi_file_path)`

---

## Dependencies

### Optional Dependency Group: [transcription]

```toml
# In pyproject.toml
[project.optional-dependencies]
transcription = [
    "madmom>=0.16.1",        # Better onset/beat detection
    "crepe>=0.0.12",         # Pitch detection
    "music21>=9.0.0",        # Rhythm quantization
    "mir_eval>=0.7",         # Evaluation metrics
    "mido>=1.3.0",           # MIDI file handling
]
```

**Install**: `pip install guitarprotool[transcription]`
**Size**: ~500MB total (music21 includes large corpora)
**Strategy**: Optional dependency, lazy-loaded when feature is used

---

## Testing & Validation

### Ground Truth Test Suite

**Phase 1 Setup** (5 songs):
1. Select simple root-note bass songs (existing GP tabs)
2. Extract audio from YouTube/source
3. Manually verify tabs are correct
4. Create fixtures in `tests/fixtures/ground_truth/`

**Phase 2 Expansion** (10 songs total):
5. Add songs with more complexity (walking bass, eighths)
6. Mix: Different genres, tempos, recording quality

### Evaluation Metrics (mir_eval)
- **Onset Detection**: Precision, Recall, F-measure
- **Pitch Accuracy**: Percentage of correct notes
- **Rhythm Accuracy**: Percentage of correct durations
- **Overall Transcription**: Note-level F-measure (pitch + onset + duration)

### Success Criteria
- **Clean recordings**: 70%+ overall accuracy
- **Live recordings**: 60%+ overall accuracy
- **User goal**: 80%+ on simple root-note bass
- **Manual refinement time**: < 5 minutes per song

---

## Expected Accuracy & Challenges

### Realistic Accuracy Targets

**Clean Studio Recordings**:
- Pitch detection: 95-98% (CREPE on isolated bass)
- Onset detection: 90-95% (madmom)
- Rhythm quantization: 70-85% (simple patterns)
- **Overall**: 65-80% fully correct notes

**Live/Noisy Recordings**:
- Pitch detection: 75-85% (background noise, effects)
- Onset detection: 80-90% (less clear attacks)
- Rhythm quantization: 60-75% (tempo drift, rubato)
- **Overall**: 50-65% fully correct notes

### Key Technical Challenges

**Bass-Specific Issues**:
- Low frequencies harder to detect accurately
- String noise, fret buzz, harmonics
- Effects processing (distortion, compression, chorus)
- Sustained notes (no clear attack for onset detection)

**Rhythm Complexity**:
- Syncopation detection (offbeat accents)
- Triplets vs swing feel (quantization ambiguity)
- Ghost notes (very quiet, often missed)
- Rubato sections (tempo changes)

**Notation Ambiguity**:
- Same pitch, multiple fret positions (e.g., E on 5th fret of A string vs open E)
- Requires harmonic context or hand position heuristics
- Slides/bends (continuous pitch vs discrete notes)

**Live Recording Artifacts**:
- Tempo drift (adaptive sync already handles this!)
- Bleed from other instruments (drums, guitar)
- Dynamic range variations

---

## Risk Mitigation for 80%+ Accuracy Goal

### Strategies

1. **Bass Isolation Quality** (Most Critical)
   - Already using Demucs v4 (state-of-the-art)
   - Test isolation quality on ground truth songs
   - Fallback: Allow user to provide pre-isolated bass tracks

2. **Simple Root Notes Focus**
   - Intentionally limiting scope increases accuracy
   - Root notes have clear onsets, sustained durations
   - Document limitation clearly in UI

3. **Multiple Algorithm Options**
   - madmom vs librosa for onset detection
   - CREPE vs Basic Pitch for pitch tracking
   - Test both, use best for each song type
   - User override option if auto-detection fails

4. **Confidence-Based Filtering**
   - Only include high-confidence detections
   - Flag uncertain notes for manual review
   - Better to have fewer notes with high accuracy

5. **Iterative Refinement**
   - Measure baseline in Phase 1
   - Identify failure modes from ground truth comparison
   - Tune algorithms based on actual errors
   - Re-test after each improvement

6. **User Feedback Loop**
   - User tests on real songs throughout development
   - Provide feedback on specific failures
   - Adjust algorithms/heuristics based on feedback

### Contingency Plan

If 80% proves unattainable:
- Identify achievable accuracy (70%? 75%?)
- Discuss whether that's useful enough
- Consider alternative approaches (ML model fine-tuning, manual correction UI)

---

## Competitive Analysis

### Existing Bass Transcription Tools

**Transcribe!** (Commercial)
- Slow down audio, loop sections, manual pitch aids
- **Still requires human to write tab**

**AnthemScore** (Commercial ML)
- Auto-transcription using neural networks
- Outputs MIDI and sheet music
- **Generic, not bass-optimized**

**Sonic Visualiser** (Free)
- Research tool for audio analysis
- Requires manual plugin configuration
- **No automated transcription**

**Guitar Pro 8 Built-in**
- Audio track import (we already do this!)
- **No auto-transcription feature**

### Our Competitive Advantage

- **Bass-specific optimization** (Demucs isolation + CREPE)
- **Guitar Pro native integration** (inject directly into .gp files)
- **Free and open source**
- **Tailored workflow** (YouTube → Bass tab in one command)

---

## Success Metrics by Phase

| Phase | Feature | Accuracy Target | Success Criteria |
|-------|---------|-----------------|------------------|
| 1 | Better beat detection | +10-15% F-measure | Onset detection improved |
| 2 | Pitch detection | 95%+ on simple bass | CREPE detects notes accurately |
| 3 | Rhythm quantization | 80%+ simple patterns | Durations mostly correct |
| 4 | MIDI generation | 80%+ overall | Combined pitch+rhythm ≥80% |
| 5 | GP tab injection | 80%+ overall | Tabs readable in GP8 |
| 6 | CLI integration | User satisfaction | Workflow is usable |

**Final Success**: User can transcribe simple root-note bass tabs with 80%+ accuracy, spending < 5 minutes on manual corrections per song.

---

## Next Steps

### Before Starting Implementation

1. **Ground Truth Preparation**
   - Provide 5 simple root-note bass GP files
   - Share corresponding audio sources (YouTube URLs or files)
   - Validate they're suitable test cases

2. **Baseline Measurement**
   - Run current librosa beat detection on test songs
   - Measure accuracy with mir_eval
   - Document current performance

3. **Dependency Installation**
   - Install `pip install guitarprotool[transcription]` dependencies
   - Verify madmom, CREPE, mir_eval work on system
   - Test on sample audio file

### Phase 1 Implementation

- Add madmom to beat_detector.py
- Test on 5 ground truth songs
- Measure improvement vs librosa baseline
- **Go/No-Go Decision**: If improvement < 10%, investigate before proceeding

---

## References

### Research Papers
- CREPE: Kim et al., "CREPE: A Convolutional Representation for Pitch Estimation," ICASSP 2018
- Basic Pitch: Bittner et al., "A Lightweight Instrument-Agnostic Model for Polyphonic Note Transcription and Multipitch Estimation," ICASSP 2022
- madmom: Böck et al., "madmom: A New Python Audio and Music Signal Processing Library," ISMIR 2016
- mir_eval: Raffel et al., "mir_eval: A Transparent Implementation of Common MIR Metrics," ISMIR 2014

### Libraries
- CREPE: [github.com/marl/crepe](https://github.com/marl/crepe)
- Basic Pitch: [github.com/spotify/basic-pitch](https://github.com/spotify/basic-pitch)
- madmom: [github.com/CPJKU/madmom](https://github.com/CPJKU/madmom)
- music21: [web.mit.edu/music21](https://web.mit.edu/music21)
- mir_eval: [github.com/mir-evaluation/mir_eval](https://github.com/mir-evaluation/mir_eval)

---

## Conclusion

**Feasibility**: HIGH - All required tools exist and are battle-tested
**Innovation**: MEDIUM - Combining existing tools in bass-optimized pipeline
**Accuracy**: REALISTIC - 60-80% for clean audio, with manual refinement
**Timeline**: 4 months to fully integrated feature
**Risk**: Medium - 80% accuracy is ambitious but achievable with focus on simple patterns
**Value**: HIGH - Automated transcription saves hours per song

**Recommended Action**: Begin Phase 1 (madmom beat detection improvement) to validate approach before committing to full pipeline.
