package co.edu.ucc.civia;

import android.Manifest;
import android.annotation.SuppressLint;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.MediaRecorder;
import android.os.SystemClock;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;
import java.io.ByteArrayOutputStream;

@CapacitorPlugin(name = "CiviaAudio", permissions = @Permission(alias = "microphone", strings = Manifest.permission.RECORD_AUDIO))
public final class CiviaAudioPlugin extends Plugin {
    private static final String AUDIO_ERROR = "No se pudo grabar la nota de voz.";
    private static final int CHANNEL = AudioFormat.CHANNEL_IN_MONO;
    private static final int ENCODING = AudioFormat.ENCODING_PCM_16BIT;
    private Recording active;

    private static final class Recording {
        private volatile boolean stopped;
        private volatile boolean cancelled;
        private boolean finished;
        private byte[] wav;
        private PluginCall finish;
    }

    @PluginMethod public void start(PluginCall call) {
        if (getPermissionState("microphone") == PermissionState.GRANTED) capture(call);
        else requestPermissionForAlias("microphone", call, "microphoneResult");
    }

    @PermissionCallback private void microphoneResult(PluginCall call) {
        if (getPermissionState("microphone") == PermissionState.GRANTED) capture(call);
        else call.reject("Permite el acceso al micrófono para grabar una nota de voz.", "permission");
    }

    private synchronized void capture(PluginCall call) {
        if (active != null) { call.reject(AUDIO_ERROR); return; }
        var recording = new Recording();
        active = recording;
        new Thread(() -> record(recording, call), "civia-microphone").start();
    }

    @SuppressLint("MissingPermission") // start and the permission callback require RECORD_AUDIO first.
    private void record(Recording recording, PluginCall start) {
        AudioRecord microphone = null;
        boolean started = false;
        byte[] file = null;
        try {
            int minimum = AudioRecord.getMinBufferSize(WaveAudio.SAMPLE_RATE, CHANNEL, ENCODING);
            if (minimum <= 0 || recording.cancelled) throw new IllegalStateException();
            microphone = new AudioRecord(MediaRecorder.AudioSource.MIC, WaveAudio.SAMPLE_RATE, CHANNEL, ENCODING, Math.max(minimum, 4096));
            if (microphone.getState() != AudioRecord.STATE_INITIALIZED || recording.stopped) throw new IllegalStateException();
            microphone.startRecording();
            if (microphone.getRecordingState() != AudioRecord.RECORDSTATE_RECORDING) throw new IllegalStateException();
            started = true;
            start.resolve();
            var pcm = new ByteArrayOutputStream();
            var buffer = new byte[2048];
            long deadline = SystemClock.elapsedRealtime() + 60_000;
            while (!recording.stopped && pcm.size() < WaveAudio.MAX_PCM_BYTES && SystemClock.elapsedRealtime() < deadline) {
                int limit = Math.min(buffer.length, WaveAudio.MAX_PCM_BYTES - pcm.size());
                int read = microphone.read(buffer, 0, limit, AudioRecord.READ_BLOCKING);
                if (read < 0) throw new IllegalStateException();
                pcm.write(buffer, 0, read);
            }
            if (!recording.cancelled) file = WaveAudio.encode(pcm.toByteArray());
        } catch (RuntimeException error) {
            if (!started) start.reject(AUDIO_ERROR);
        } finally {
            if (microphone != null) {
                if (started) { try { microphone.stop(); } catch (IllegalStateException ignored) { } }
                microphone.release();
            }
            complete(recording, file, started);
        }
    }

    private synchronized void complete(Recording recording, byte[] file, boolean started) {
        recording.finished = true;
        recording.wav = file;
        if (recording.finish != null) finish(recording);
        else if (!started || recording.cancelled) active = null;
    }

    @PluginMethod public synchronized void stop(PluginCall call) {
        if (active == null || active.finish != null) { call.reject(AUDIO_ERROR); return; }
        active.stopped = true;
        active.finish = call;
        if (active.finished) finish(active);
    }

    private void finish(Recording recording) {
        active = null;
        if (recording.cancelled || recording.wav == null) recording.finish.reject(AUDIO_ERROR);
        else recording.finish.resolve(new JSObject().put("base64", Base64.encodeToString(recording.wav, Base64.NO_WRAP)));
    }

    @PluginMethod public synchronized void cancel(PluginCall call) {
        cancelActive();
        call.resolve();
    }

    private void cancelActive() {
        if (active == null) return;
        active.stopped = true;
        active.cancelled = true;
        if (active.finished) active = null;
    }

    @Override protected synchronized void handleOnPause() { if (active != null) active.stopped = true; }

    @Override protected synchronized void handleOnDestroy() { cancelActive(); }
}
