# Guitar Pro 8 File Format Documentation

## Overview

This document details the Guitar Pro 8 (.gp) file format structure, specifically focusing on audio track integration. All findings are based on reverse-engineering actual .gp files created by Guitar Pro 8.

**Status:** Last updated 2025-12-03

## File Structure

### Archive Format

Guitar Pro 8 files are **ZIP archives** with the following structure:

```
mysong.gp (ZIP archive)
├── Content/
│   ├── Assets/                    # Audio files (UUID-named MP3s)
│   │   └── {uuid}.mp3
│   ├── ScoreViews/                # View configurations
│   │   ├── 1.gpsv
│   │   └── 2.gpsv
│   ├── Stylesheets/               # Styling files
│   │   ├── score.gpss
│   │   ├── scoreview1.gpss
│   │   └── scoreview2.gpss
│   ├── score.gpif                 # Main XML file (tab data, audio metadata)
│   ├── Preferences.json
│   ├── LayoutConfiguration
│   ├── BinaryStylesheet
│   └── PartConfiguration
├── meta.json                      # File metadata
└── VERSION                        # Format version
```

### Key Observations

- **Audio files are stored in `Content/Assets/`**, NOT `Content/Audio/`
- Audio filenames use the format `{SHA1-UUID}.mp3`
- All tab data, tempo, measures, and audio metadata are in `score.gpif` XML

## score.gpif XML Structure

### High-Level Hierarchy

```xml
<GPIF>
  <GPRevision>...</GPRevision>
  <Score>...</Score>
  <MasterTrack>
    <Tracks>0</Tracks>
    <Automations>
      <Automation><Type>Tempo</Type>...</Automation>
      <Automation><Type>SyncPoint</Type>...</Automation>
      <!-- More SyncPoint automations -->
    </Automations>
    <RSE>...</RSE>
  </MasterTrack>
  <BackingTrack>
    <!-- Audio track metadata -->
  </BackingTrack>
  <Tracks>
    <Track id="0">...</Track>
    <!-- Instrument tracks -->
  </Tracks>
  <MasterBars>...</MasterBars>
  <Bars>...</Bars>
  <Voices>...</Voices>
  <Beats>...</Beats>
  <Notes>...</Notes>
  <Rhythms>...</Rhythms>
  <Assets>
    <Asset id="0">...</Asset>
  </Assets>
  <ScoreViews>...</ScoreViews>
</GPIF>
```

## Audio Track Elements

### 1. BackingTrack Element

Located between `<MasterTrack>` and `<Tracks>`, the `<BackingTrack>` element defines the audio track configuration.

**Full Structure:**

```xml
<BackingTrack>
  <IconId>21</IconId>
  <Color>0 0 0</Color>
  <Name><![CDATA[Audio Track]]></Name>
  <ShortName><![CDATA[a.track]]></ShortName>
  <PlaybackState>Solo</PlaybackState>         <!-- Solo, Default, or Mute -->
  <ChannelStrip>
    <Parameters>0.500000 0.500000 0.500000 0.500000 0.500000 0.500000 0.500000 0.500000 0.500000 0.000000 0.500000 0.500000 0.800000 0.500000 0.500000 0.500000</Parameters>
  </ChannelStrip>
  <Enabled>true</Enabled>
  <Source>Local</Source>                      <!-- Local or YouTube -->
  <AssetId>0</AssetId>                         <!-- References Asset id -->
  <YouTubeVideoUrl></YouTubeVideoUrl>
  <Filter>6</Filter>
  <FramesPerPixel>100</FramesPerPixel>         <!-- Waveform zoom level -->
  <FramePadding>0</FramePadding>               <!-- Time offset (audio frames, can be negative) -->
  <Semitones>0</Semitones>                     <!-- Pitch shift -->
  <Cents>0</Cents>                             <!-- Fine pitch adjustment -->
</BackingTrack>
```

**Element Descriptions:**

- **IconId**: Display icon (21 = audio track icon)
- **Color**: RGB values (0 0 0 = black)
- **Name**: Display name shown in track list
- **ShortName**: Abbreviated name
- **PlaybackState**: Playback mode
  - `Solo` - Only this track plays
  - `Default` - Normal playback
  - `Mute` - Track muted
- **ChannelStrip/Parameters**: 16 float values (0.0-1.0) for audio processing (EQ, volume, etc.)
- **Enabled**: Whether track is enabled
- **Source**: Audio source type
  - `Local` - File embedded in .gp archive
  - `YouTube` - Stream from YouTube (URL in YouTubeVideoUrl)
- **AssetId**: References `<Asset id="X">` in Assets section
- **Filter**: Unknown purpose (value 6 observed in both samples)
- **FramesPerPixel**: Waveform display zoom (higher = more zoomed out)
- **FramePadding**: Audio offset in frames (negative = shift audio earlier)
- **Semitones**: Pitch shift in semitones (-12 to +12)
- **Cents**: Fine pitch adjustment in cents (-100 to +100)

### 2. Assets Element

Located near the end of the XML (after `<Rhythms>`), defines audio file references.

**Structure:**

```xml
<Assets>
  <Asset id="0">
    <OriginalFilePath><![CDATA[D:/Guitar Pro Tabs/Music Files/song.mp3]]></OriginalFilePath>
    <OriginalFileSha1><![CDATA[d47e6e00-5294-5fba-a78d-aad81b5856ca]]></OriginalFileSha1>
    <EmbeddedFilePath><![CDATA[Content/Assets/d47e6e00-5294-5fba-a78d-aad81b5856ca.mp3]]></EmbeddedFilePath>
  </Asset>
</Assets>
```

**Element Descriptions:**

- **Asset id**: Unique identifier (referenced by BackingTrack/AssetId)
- **OriginalFilePath**: Path where audio was imported from (for reference only)
- **OriginalFileSha1**: SHA1 hash used as UUID for embedded filename
- **EmbeddedFilePath**: Path within .gp ZIP archive (always `Content/Assets/{uuid}.mp3`)

### 3. SyncPoint Automations

Sync points synchronize audio playback with tab measures. They're stored as `<Automation>` elements within `<MasterTrack><Automations>`.

**Structure:**

```xml
<Automation>
  <Type>SyncPoint</Type>
  <Linear>false</Linear>
  <Bar>0</Bar>                                 <!-- Bar number (0-indexed) -->
  <Position>0</Position>                       <!-- Position within bar (0 = start) -->
  <Visible>true</Visible>
  <Value>
    <BarIndex>0</BarIndex>
    <BarOccurrence>0</BarOccurrence>
    <ModifiedTempo>79.883</ModifiedTempo>      <!-- Detected tempo in audio -->
    <OriginalTempo>80</OriginalTempo>          <!-- Tab tempo -->
    <FrameOffset>0</FrameOffset>               <!-- Audio frame position -->
  </Value>
</Automation>
```

**Element Descriptions:**

- **Type**: Always `SyncPoint` for sync automations
- **Linear**: Always `false` for sync points
- **Bar**: Bar/measure number (0-indexed) where sync occurs
- **Position**: Position within bar (0 = start of bar)
- **Visible**: Always `true`
- **Value/BarIndex**: Same as Bar (redundant)
- **Value/BarOccurrence**: Always `0` (likely for repeat sections)
- **Value/ModifiedTempo**: Detected tempo in audio at this point (BPM)
- **Value/OriginalTempo**: Tempo specified in tab (BPM)
- **Value/FrameOffset**: Audio frame position (sample number at 44.1kHz)

### SyncPoint Placement Strategy

**Sample 1 (Air - La Femme D'Argent):**
- Bars: 0, 5, 6, 9, 41, 59, 81, 85, 96
- Tempo: 80 BPM (original)
- Spacing: Irregular, possibly manually placed

**Sample 2 (Muse - Thought Contagion):**
- Bars: 0, 1, 2, 3, 5 (early bars more frequent)
- Tempo: 70 BPM (original)
- Spacing: More regular at start, then sparse

**Observations:**
- Sync points handle BPM drift in recordings (ModifiedTempo varies slightly)
- More sync points = tighter alignment but larger XML
- No consistent pattern (not strictly every N bars)
- First sync point always at Bar 0, FrameOffset 0

## Implementation Notes

### Adding Audio to a .gp File

**Required steps:**

1. **Copy audio file** to `Content/Assets/` with UUID filename
   - Generate UUID (SHA1 hash of file or random)
   - Filename format: `{uuid}.mp3`
   - Recommended: MP3, 192kbps, 44.1kHz

2. **Add `<BackingTrack>` element** after `<MasterTrack>`, before `<Tracks>`
   - Use template from section "BackingTrack Element"
   - Set `<AssetId>` to match Asset id

3. **Add `<Asset>` element** in `<Assets>` section
   - Set id to match BackingTrack/AssetId
   - Set OriginalFilePath (can be arbitrary)
   - Set OriginalFileSha1 to UUID
   - Set EmbeddedFilePath to `Content/Assets/{uuid}.mp3`

4. **Add SyncPoint automations** in `<MasterTrack><Automations>`
   - Add after any existing Tempo automation
   - Create at least one sync point at Bar 0
   - Calculate FrameOffset from beat detection

### FrameOffset Calculation

**Formula:**
```
FrameOffset = (time_in_seconds) * sample_rate
```

Where:
- `time_in_seconds` = time position of bar in audio
- `sample_rate` = 44100 Hz (standard for MP3)

**Example:**
Bar starts at 5.5 seconds into audio:
```
FrameOffset = 5.5 * 44100 = 242550
```

### Tempo Calculation

**ModifiedTempo** should reflect the actual tempo detected in the audio between sync points.

**Formula:**
```
ModifiedTempo = (beats_in_section / duration_in_seconds) * 60
```

For simple cases where audio matches tab tempo, set:
```
ModifiedTempo = OriginalTempo
```

### XML Formatting Preservation

**CRITICAL:** Guitar Pro 8 is sensitive to XML formatting changes. When modifying score.gpif:

1. Use **lxml** (NOT ElementTree) for XML parsing
2. Preserve original indentation (2 spaces per level)
3. Preserve CDATA sections: `<![CDATA[text]]>`
4. Use `pretty_print=True` when writing, but match original spacing
5. Test modified files by opening in Guitar Pro 8

### ZIP Compression

When repackaging .gp files:

1. Preserve original compression method for each file (store vs deflate)
2. Match compression level exactly
3. Preserve file order in ZIP directory
4. The `GPFile` class handles this automatically via `_compression_info`

## Sample Data

### Minimal BackingTrack (Safe Defaults)

```xml
<BackingTrack>
  <IconId>21</IconId>
  <Color>0 0 0</Color>
  <Name><![CDATA[Audio Track]]></Name>
  <ShortName><![CDATA[a.track]]></ShortName>
  <PlaybackState>Default</PlaybackState>
  <ChannelStrip>
    <Parameters>0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.5 0.0 0.5 0.5 0.8 0.5 0.5 0.5</Parameters>
  </ChannelStrip>
  <Enabled>true</Enabled>
  <Source>Local</Source>
  <AssetId>0</AssetId>
  <YouTubeVideoUrl></YouTubeVideoUrl>
  <Filter>6</Filter>
  <FramesPerPixel>100</FramesPerPixel>
  <FramePadding>0</FramePadding>
  <Semitones>0</Semitones>
  <Cents>0</Cents>
</BackingTrack>
```

### Minimal SyncPoint (First Bar)

```xml
<Automation>
  <Type>SyncPoint</Type>
  <Linear>false</Linear>
  <Bar>0</Bar>
  <Position>0</Position>
  <Visible>true</Visible>
  <Value>
    <BarIndex>0</BarIndex>
    <BarOccurrence>0</BarOccurrence>
    <ModifiedTempo>80.0</ModifiedTempo>
    <OriginalTempo>80</OriginalTempo>
    <FrameOffset>0</FrameOffset>
  </Value>
</Automation>
```

## Testing Checklist

When implementing audio injection:

- [ ] Modified .gp file opens in Guitar Pro 8 without errors
- [ ] Audio track appears in track list with correct name
- [ ] Audio plays when tab is played
- [ ] Audio is synchronized with tab at sync points
- [ ] Pitch shift controls work (Semitones/Cents)
- [ ] Playback state controls work (Solo/Mute/Default)
- [ ] File size is reasonable (audio properly embedded)
- [ ] Re-saving in GP8 preserves injected audio

## Unknown Elements

**Elements requiring further investigation:**

1. **Filter** (value 6 in samples) - Purpose unknown
2. **ChannelStrip/Parameters** - Exact mapping of 16 float values unknown
3. **BarOccurrence** - Always 0, purpose unclear (repeats?)
4. **Position** - Always 0 in samples, but might support mid-bar sync points
5. **Linear** - Always false for SyncPoint, might affect interpolation

## References

- Sample files analyzed:
  - `sample-files/Air - La Femme D'Argent (with audio).gp`
  - `sample-files/Muse - Thought Contagion (with audio).gp`
- Guitar Pro 8 version: Unknown (determined from sample files)
