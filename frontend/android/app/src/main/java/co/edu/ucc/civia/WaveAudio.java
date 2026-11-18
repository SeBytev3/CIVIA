package co.edu.ucc.civia;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;

final class WaveAudio {
    static final int SAMPLE_RATE = 16_000;
    static final int MAX_PCM_BYTES = 60 * SAMPLE_RATE * Short.BYTES;

    static byte[] encode(byte[] pcm) {
        if (pcm.length == 0 || pcm.length > MAX_PCM_BYTES || pcm.length % Short.BYTES != 0) throw new IllegalArgumentException();
        return ByteBuffer.allocate(44 + pcm.length).order(ByteOrder.LITTLE_ENDIAN)
            .put("RIFF".getBytes(StandardCharsets.US_ASCII)).putInt(36 + pcm.length)
            .put("WAVEfmt ".getBytes(StandardCharsets.US_ASCII)).putInt(16)
            .putShort((short) 1).putShort((short) 1).putInt(SAMPLE_RATE)
            .putInt(SAMPLE_RATE * Short.BYTES).putShort((short) Short.BYTES).putShort((short) 16)
            .put("data".getBytes(StandardCharsets.US_ASCII)).putInt(pcm.length).put(pcm).array();
    }
}
