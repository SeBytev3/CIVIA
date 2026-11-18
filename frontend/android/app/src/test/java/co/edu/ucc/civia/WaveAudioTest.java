package co.edu.ucc.civia;

import static org.junit.Assert.*;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import org.junit.Test;

public class WaveAudioTest {
    @Test public void monoPcmHasAValidWaveHeaderAndSampleBytes() {
        byte[] samples = {0, 0, (byte) 0xff, 0x7f, 0, (byte) 0x80};
        byte[] file = WaveAudio.encode(samples);
        var fields = ByteBuffer.wrap(file).order(ByteOrder.LITTLE_ENDIAN);
        assertEquals("RIFF", new String(file, 0, 4, StandardCharsets.US_ASCII));
        assertEquals(file.length - 8, fields.getInt(4));
        assertEquals("WAVEfmt ", new String(file, 8, 8, StandardCharsets.US_ASCII));
        assertEquals(1, fields.getShort(22));
        assertEquals(16_000, fields.getInt(24));
        assertEquals(16, fields.getShort(34));
        assertEquals("data", new String(file, 36, 4, StandardCharsets.US_ASCII));
        assertEquals(samples.length, fields.getInt(40));
        assertArrayEquals(samples, java.util.Arrays.copyOfRange(file, 44, file.length));
    }

    @Test public void rejectsPartialSamplesAndRecordingsOverOneMinute() {
        assertThrows(IllegalArgumentException.class, () -> WaveAudio.encode(new byte[1]));
        assertThrows(IllegalArgumentException.class, () -> WaveAudio.encode(new byte[WaveAudio.MAX_PCM_BYTES + 2]));
        assertTrue(WaveAudio.MAX_PCM_BYTES + 44 < 5 * 1024 * 1024);
    }
}
