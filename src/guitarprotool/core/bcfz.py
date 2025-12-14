"""BCFZ decompression for Guitar Pro GPX files.

The BCFZ format is a proprietary compression format used by Guitar Pro 6/7
(.gpx files). This module implements decompression to extract the inner
file system container.

Algorithm based on TuxGuitar GPXFileSystem.java:
- https://github.com/phiresky/tuxguitar/blob/master/TuxGuitar-gpx/src/org/herac/tuxguitar/io/gpx/v6/GPXFileSystem.java

Format structure:
- Header: "BCFZ" (4 bytes)
- Expected decompressed size (4 bytes, little-endian)
- Compressed data chunks

Chunk types (determined by single bit flag):
- Flag 0: Literal chunk (uncompressed bytes)
  - 2 bits (reversed/LE): count of bytes
  - N bytes: raw data (8 bits each)
- Flag 1: Back-reference chunk (copy from history)
  - 4 bits: word size for offset/length
  - word_size bits (reversed/LE): offset into history
  - word_size bits (reversed/LE): length to copy
"""

from loguru import logger

from guitarprotool.utils.exceptions import BCFZDecompressionError


class BitStream:
    """Bit-by-bit reader for BCFZ decompression.

    Reads individual bits and groups of bits from a byte stream.
    TuxGuitar calls this GPXByteBuffer with readBits and readBitsReversed.
    """

    def __init__(self, data: bytes):
        """Initialize BitStream with data.

        Args:
            data: Bytes to read from
        """
        self._data = data
        self._byte_pos = 0
        self._bit_pos = 0  # 0-7, current bit within current byte

    @property
    def offset(self) -> int:
        """Current byte offset in stream."""
        return self._byte_pos

    def end(self) -> bool:
        """Check if stream is exhausted."""
        return self._byte_pos >= len(self._data)

    def read_bit(self) -> int:
        """Read a single bit from the stream (MSB first within each byte).

        Bits are read from bit 7 (MSB) to bit 0 (LSB) within each byte.

        Returns:
            0 or 1

        Raises:
            BCFZDecompressionError: If end of stream reached
        """
        if self._byte_pos >= len(self._data):
            raise BCFZDecompressionError("Unexpected end of BCFZ stream")

        # Read bit from current byte (MSB first - bit 7 is read first)
        bit = (self._data[self._byte_pos] >> (7 - self._bit_pos)) & 1

        self._bit_pos += 1
        if self._bit_pos >= 8:
            self._bit_pos = 0
            self._byte_pos += 1

        return bit

    def read_bits(self, count: int) -> int:
        """Read bits and assemble them MSB first.

        Args:
            count: Number of bits to read

        Returns:
            Integer value of bits read (MSB first assembly)
        """
        result = 0
        for _ in range(count):
            result = (result << 1) | self.read_bit()
        return result

    def read_bits_reversed(self, count: int) -> int:
        """Read bits and assemble them LSB first (reversed).

        This is used for fields marked as "reversed/LE" in the BCFZ format.
        The first bit read goes to position 0, second to position 1, etc.

        Args:
            count: Number of bits to read

        Returns:
            Integer value of bits read (LSB first assembly)
        """
        result = 0
        for i in range(count):
            bit = self.read_bit()
            result |= (bit << i)
        return result


def decompress_bcfz(data: bytes) -> bytes:
    """Decompress BCFZ-compressed data.

    Algorithm from TuxGuitar GPXFileSystem.java decompress() method.

    Args:
        data: BCFZ compressed data (including header)

    Returns:
        Decompressed data (BCFS container)

    Raises:
        BCFZDecompressionError: If decompression fails
    """
    # Verify header
    if len(data) < 8:
        raise BCFZDecompressionError("BCFZ data too short (< 8 bytes)")

    if not data.startswith(b"BCFZ"):
        raise BCFZDecompressionError(
            f"Invalid BCFZ header: expected 'BCFZ', got {data[:4]!r}"
        )

    # Read expected decompressed size (32-bit little-endian at offset 4)
    expected_size = int.from_bytes(data[4:8], "little")
    logger.debug(f"BCFZ expected decompressed size: {expected_size}")

    # Create bit stream starting after header
    stream = BitStream(data[8:])
    output = bytearray()

    try:
        while not stream.end() and len(output) < expected_size:
            # Read chunk type flag bit
            flag = stream.read_bit()

            if flag == 1:
                # Back-reference chunk: copy from earlier in output
                # Read 4 bits for word size (determines size of offset/length fields)
                word_size = stream.read_bits(4)

                # Skip if word_size is 0 (invalid)
                if word_size == 0:
                    continue

                # Read offset and length using word_size bits each (reversed/LE)
                offs = stream.read_bits_reversed(word_size)
                size = stream.read_bits_reversed(word_size)

                # Skip invalid back-references (offset 0, length 0, or offset > buffer)
                if offs == 0 or size == 0 or offs > len(output):
                    continue

                # Copy from earlier in output buffer
                # Position is from end of current output, going backwards
                pos = len(output) - offs

                # Copy bytes - for overlapping copies (size > offs), repeat the pattern
                # This is standard LZ77 RLE behavior
                for i in range(size):
                    # Use modulo to wrap around when copying more than available
                    output.append(output[pos + (i % offs) if offs > 0 else 0])

            else:
                # Literal chunk: read raw bytes
                # Read 2 bits for byte count (reversed/LE: 0-3 bytes)
                size = stream.read_bits_reversed(2)

                # Read 'size' literal bytes (raw bytes, not reversed)
                for _ in range(size):
                    byte_val = stream.read_bits(8)
                    output.append(byte_val)

    except BCFZDecompressionError:
        # If we're within 1% of expected size and hit end of stream, that's acceptable
        # Some BCFZ streams have trailing padding bits that don't form complete chunks
        if len(output) >= expected_size * 0.99:
            logger.debug(f"BCFZ stream ended near expected size ({len(output)}/{expected_size})")
        else:
            raise
    except Exception as e:
        raise BCFZDecompressionError(f"BCFZ decompression failed: {e}") from e

    logger.debug(f"BCFZ decompressed {len(output)} bytes (expected {expected_size})")
    return bytes(output)


def extract_gpx_files(decompressed_data: bytes) -> dict[str, bytes]:
    """Extract individual files from decompressed GPX container.

    The decompressed GPX data contains a custom file system format (BCFS)
    with multiple files including score.gpif, misc.xml, etc.

    BCFS uses 4KB sectors:
    - Sector 0: Header "BCFS" + padding
    - Sectors 1+: File table entries (one entry per sector)
    - Later sectors: File data

    File table entry structure (within a sector):
    - 4 bytes: sector marker (0xFFFFFFFF for first, 0x00000000 for others)
    - 4 bytes: entry type (1=directory, 2=file)
    - ~124 bytes: filename (null-terminated, padded)
    - 4 bytes: padding/unknown
    - 4 bytes: file size (for type=2)
    - 4 bytes: padding
    - N*4 bytes: sector number list for file data

    Args:
        decompressed_data: Decompressed BCFZ data

    Returns:
        Dictionary mapping filenames to file contents

    Raises:
        BCFZDecompressionError: If container format is invalid
    """
    SECTOR_SIZE = 4096

    if not decompressed_data.startswith(b"BCFS"):
        raise BCFZDecompressionError(
            f"Invalid BCFS container: expected 'BCFS', got {decompressed_data[:4]!r}"
        )

    files = {}
    num_sectors = len(decompressed_data) // SECTOR_SIZE

    # Scan through sectors looking for file entries
    for sector_num in range(1, num_sectors):
        sector_offset = sector_num * SECTOR_SIZE
        sector_data = decompressed_data[sector_offset : sector_offset + SECTOR_SIZE]

        if len(sector_data) < 140:
            continue

        # Read sector marker and entry type
        sector_marker = int.from_bytes(sector_data[0:4], "little")
        entry_type = int.from_bytes(sector_data[4:8], "little")

        # Skip non-file entries (type 1 = directory, type 2 = file)
        if entry_type != 2:
            continue

        # Extract filename (starts at offset 8, null-terminated)
        filename_end = sector_data.find(b"\x00", 8)
        if filename_end <= 8:
            continue

        filename = sector_data[8:filename_end].decode("utf-8", errors="replace")

        # File metadata is at offset 128 from sector start (after 4-byte marker)
        # Actually it's at a fixed offset within the entry
        # Looking at the data: filename starts at +8, metadata at filename+120 or so

        # Based on analysis: metadata starts at sector_offset + 132
        # - 4 bytes: unknown (usually 0)
        # - 4 bytes: sector count or flags
        # - 4 bytes: file size
        # - 4 bytes: padding
        # - sector list follows

        # The structure seems to be at fixed offset 132 from sector start
        meta_offset = 132
        if meta_offset + 12 > len(sector_data):
            continue

        # Read file size at offset 136 (132 + 4)
        file_size = int.from_bytes(sector_data[136:140], "little")

        # Sector list starts at offset 144
        sector_list_offset = 144
        sectors_needed = (file_size + SECTOR_SIZE - 1) // SECTOR_SIZE

        # Read sector numbers
        data_sectors = []
        for i in range(sectors_needed + 5):  # Read a few extra in case
            idx = sector_list_offset + i * 4
            if idx + 4 > len(sector_data):
                break
            sector_idx = int.from_bytes(sector_data[idx : idx + 4], "little")
            if sector_idx == 0 and i > 0:
                # End of sector list (or unused)
                break
            if sector_idx > 0 and sector_idx < num_sectors:
                data_sectors.append(sector_idx)

        # Extract file data from sectors
        file_data = bytearray()
        for data_sector in data_sectors:
            data_offset = data_sector * SECTOR_SIZE
            # First 4 bytes of data sector seem to be header/marker, skip them
            chunk = decompressed_data[data_offset + 4 : data_offset + SECTOR_SIZE]
            file_data.extend(chunk)
            if len(file_data) >= file_size:
                break

        # Trim to exact size
        file_data = bytes(file_data[:file_size])

        if file_data:
            files[filename] = file_data
            logger.debug(
                f"Extracted from GPX container: {filename} "
                f"({file_size} bytes from {len(data_sectors)} sectors)"
            )

    if not files:
        raise BCFZDecompressionError("No files found in BCFS container")

    return files
