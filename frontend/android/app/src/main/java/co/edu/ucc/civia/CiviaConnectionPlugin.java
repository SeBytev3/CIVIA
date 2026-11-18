package co.edu.ucc.civia;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.BitmapFactory;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.zxing.BinaryBitmap;
import com.google.zxing.RGBLuminanceSource;
import com.google.zxing.common.HybridBinarizer;
import com.google.zxing.qrcode.QRCodeReader;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.Request;
import okhttp3.RequestBody;
import org.json.JSONObject;

@CapacitorPlugin(name = "CiviaConnection")
public final class CiviaConnectionPlugin extends Plugin {
    private static final int MAX_MEDIA = 5 * 1024 * 1024;
    private static final int MAX_ENCODED_MEDIA = ((MAX_MEDIA + 2) / 3) * 4;
    private static final MediaType JSON = MediaType.get("application/json; charset=utf-8");
    private final Object state = new Object();
    private final ThreadPoolExecutor workers = new ThreadPoolExecutor(3, 3, 30, TimeUnit.SECONDS, new ArrayBlockingQueue<>(12));
    private final Map<String, CiviaTransport.Cancellation> operations = new ConcurrentHashMap<>();
    private CiviaDiscovery discovery;
    private SharedPreferences preferences;
    private CiviaSessionVault vault;
    private Profile profile;
    private CiviaSessionVault.Session session;
    private long accountGeneration;
    private boolean discovering;

    private static final class StaleStateException extends IllegalStateException { }

    private record Profile(String key, ConnectionPolicy.Pairing pairing, CiviaTransport transport) {
        static Profile from(ConnectionPolicy.Pairing pairing) throws Exception {
            return new Profile(UUID.randomUUID().toString(), pairing, new CiviaTransport(pairing));
        }

        JSObject visible() {
            return new JSObject().put("profileId", key).put("installationId", pairing.installationId()).put("origin", pairing.origin());
        }
    }

    @Override public void load() {
        Context context = getContext();
        preferences = context.getSharedPreferences("civia_pairing", Context.MODE_PRIVATE);
        vault = new CiviaSessionVault(context);
        discovery = new CiviaDiscovery(context, event -> notifyListeners("discoveryChanged", event),
            () -> notifyListeners("networkChanged", new JSObject()));
        try {
            var saved = new JSONObject(preferences.getString("trusted", "{}"));
            profile = Profile.from(new ConnectionPolicy.Pairing(saved.getString("installationId"), saved.getString("origin"), saved.getString("pin")));
            session = vault.get(profile.pairing());
        } catch (Exception invalid) {
            profile = null;
            session = null;
        }
    }

    @PluginMethod public void getTrusted(PluginCall call) {
        synchronized (state) { call.resolve(profile == null ? new JSObject() : profile.visible()); }
    }

    @PluginMethod public void startDiscovery(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            discovering = true;
            discovery.start();
            call.resolve();
        });
    }

    @PluginMethod public void stopDiscovery(PluginCall call) {
        getActivity().runOnUiThread(() -> {
            discovering = false;
            discovery.stop();
            call.resolve();
        });
    }

    @Override protected void handleOnPause() { discovery.stop(); }

    @Override protected void handleOnResume() {
        if (discovering) discovery.start();
        notifyListeners("networkChanged", new JSObject());
    }

    @Override protected void handleOnDestroy() {
        discovery.stop();
        operations.values().forEach(CiviaTransport.Cancellation::cancel);
        workers.shutdownNow();
    }

    @PluginMethod public void pair(PluginCall call) {
        submit(call, cancellation -> {
            var encoded = ConnectionPolicy.parsePairing(call.getString("code"));
            var pairing = encoded.at(call.getString("origin", encoded.origin()));
            var candidate = Profile.from(pairing);
            Profile previous;
            synchronized (state) { previous = profile; }
            candidate.transport().verify(cancellation);
            synchronized (state) {
                if (profile != previous || cancellation.cancelled()) throw new StaleStateException();
                if (previous != null && sameIdentity(previous.pairing(), pairing)) {
                    candidate = new Profile(previous.key(), pairing, candidate.transport());
                }
                persist(candidate);
                if (previous == null || !previous.key().equals(candidate.key())) {
                    session = vault.get(pairing);
                    accountGeneration++;
                }
                profile = candidate;
            }
            call.resolve(candidate.visible());
        });
    }

    @PluginMethod public void reconnect(PluginCall call) {
        submit(call, cancellation -> {
            Profile previous;
            synchronized (state) { previous = activeProfile(call); }
            String address = call.getString("origin", previous.pairing().origin());
            var pairing = previous.pairing().at(address);
            var candidate = pairing.equals(previous.pairing()) ? previous : new Profile(previous.key(), pairing, new CiviaTransport(pairing));
            candidate.transport().verify(cancellation);
            synchronized (state) {
                if (profile != previous || cancellation.cancelled()) throw new StaleStateException();
                if (candidate != previous) {
                    persist(candidate);
                    profile = candidate;
                }
            }
            call.resolve(candidate.visible());
        });
    }

    @PluginMethod public void cachedSession(PluginCall call) {
        synchronized (state) {
            try {
                activeProfile(call);
                call.resolve(session == null ? new JSObject() : new JSObject().put("json", session.visible()));
            } catch (StaleStateException stale) { call.resolve(new JSObject()); }
        }
    }

    @PluginMethod public void request(PluginCall call) {
        submit(call, cancellation -> {
            String method = call.getString("method", "GET");
            String target = call.getString("path");
            var operation = ConnectionPolicy.operation(method, target);
            Profile scope;
            CiviaSessionVault.Session principal;
            long generation;
            synchronized (state) {
                scope = activeProfile(call);
                principal = session;
                if (operation.requiresSession() && principal == null) {
                    call.resolve(new JSObject().put("status", 401));
                    return;
                }
                if (operation == ConnectionPolicy.Operation.REPORT_UPLOAD && !principal.userId().equals(call.getString("ownerId"))) {
                    call.resolve(new JSObject().put("status", 403));
                    return;
                }
                if (operation == ConnectionPolicy.Operation.LOGOUT) dropSession(scope);
                generation = accountGeneration;
            }

            var transport = scope.transport();
            CiviaTransport.Reply reply;
            try {
                transport.verify(cancellation);
                synchronized (state) { ensureCurrent(scope, generation, cancellation); }
                Request request = buildRequest(scope, call, target, method, operation, principal);
                int limit = operation == ConnectionPolicy.Operation.BINARY ? MAX_MEDIA : 2 * 1024 * 1024;
                reply = transport.exchange(request, cancellation, limit, 35);
            } catch (java.io.IOException error) {
                if (operation != ConnectionPolicy.Operation.LOGOUT) throw error;
                // Local logout remains effective even when the server cannot revoke the short-lived token.
                call.resolve(new JSObject().put("status", 204));
                return;
            }
            synchronized (state) {
                ensureCurrent(scope, generation, cancellation);
                call.resolve(result(scope, operation, principal, reply));
            }
        });
    }

    @PluginMethod public void cancel(PluginCall call) {
        var operation = operations.get(call.getString("requestId", ""));
        if (operation != null) operation.cancel();
        call.resolve();
    }

    @PluginMethod public void decodeQr(PluginCall call) {
        submit(call, cancellation -> {
            byte[] data = media(call.getString("image"));
            var settings = new BitmapFactory.Options();
            settings.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(data, 0, data.length, settings);
            ConnectionPolicy.require(settings.outWidth > 0 && settings.outHeight > 0);
            settings.inSampleSize = 1;
            while (Math.max(settings.outWidth, settings.outHeight) / settings.inSampleSize > 1800) settings.inSampleSize *= 2;
            settings.inJustDecodeBounds = false;
            var bitmap = BitmapFactory.decodeByteArray(data, 0, data.length, settings);
            if (bitmap == null) throw new IllegalArgumentException();
            String text;
            try {
                int width = bitmap.getWidth();
                int height = bitmap.getHeight();
                int[] pixels = new int[width * height];
                bitmap.getPixels(pixels, 0, width, 0, 0, width, height);
                text = new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(new RGBLuminanceSource(width, height, pixels)))).getText();
            } finally { bitmap.recycle(); }
            ConnectionPolicy.parsePairing(text);
            call.resolve(new JSObject().put("code", text));
        });
    }

    private Profile activeProfile(PluginCall call) {
        if (profile == null || !profile.key().equals(call.getString("profileId"))) throw new StaleStateException();
        return profile;
    }

    private void ensureCurrent(Profile scope, long generation, CiviaTransport.Cancellation cancellation) {
        if (cancellation.cancelled() || profile == null || !profile.key().equals(scope.key()) || generation != accountGeneration) {
            throw new StaleStateException();
        }
    }

    private static boolean sameIdentity(ConnectionPolicy.Pairing first, ConnectionPolicy.Pairing second) {
        return first.installationId().equals(second.installationId()) && first.pin().equals(second.pin());
    }

    private void persist(Profile candidate) throws Exception {
        var pairing = candidate.pairing();
        String stored = new JSONObject().put("installationId", pairing.installationId()).put("origin", pairing.origin())
            .put("pin", pairing.pin()).toString();
        if (!preferences.edit().putString("trusted", stored).commit()) throw new IllegalStateException();
    }

    private void dropSession(Profile scope) {
        vault.clear(scope.pairing());
        session = null;
        accountGeneration++;
    }

    private JSObject result(Profile scope, ConnectionPolicy.Operation operation, CiviaSessionVault.Session principal, CiviaTransport.Reply reply) throws Exception {
        int status = reply.status();
        if (operation == ConnectionPolicy.Operation.LOGOUT) return new JSObject().put("status", 204);
        if (status == 401 && operation.requiresSession()) dropSession(scope);
        var body = new JSObject().put("status", status);
        if (status < 200 || status >= 300 || status == 204) return body;
        if (operation == ConnectionPolicy.Operation.BINARY) {
            ConnectionPolicy.require(reply.contentType().matches("(?:image|audio)/[a-zA-Z0-9+.-]+"));
            return body.put("contentType", reply.contentType()).put("base64", Base64.encodeToString(reply.bytes(), Base64.NO_WRAP));
        }
        ConnectionPolicy.require(reply.contentType().startsWith("application/json"));
        String json = new String(reply.bytes(), StandardCharsets.UTF_8);
        if (operation == ConnectionPolicy.Operation.LOGIN || operation == ConnectionPolicy.Operation.SESSION) {
            JSONObject decoded = new JSONObject(json);
            boolean login = operation == ConnectionPolicy.Operation.LOGIN;
            var updated = CiviaSessionVault.validate(decoded, login ? decoded.getString("token") : principal.token());
            if (!login && !principal.userId().equals(updated.userId())) {
                dropSession(scope);
                return new JSObject().put("status", 401);
            }
            vault.set(scope.pairing(), updated);
            session = updated;
            if (login) accountGeneration++;
            json = updated.visible();
        }
        return body.put("json", json).put("contentType", "application/json");
    }

    private static Request buildRequest(Profile scope, PluginCall call, String target, String method,
            ConnectionPolicy.Operation operation, CiviaSessionVault.Session principal) throws Exception {
        var request = scope.transport().request(target).header("Accept", operation == ConnectionPolicy.Operation.BINARY ? "image/*, audio/*" : "application/json");
        if (operation.requiresSession()) request.header("Authorization", "Bearer " + principal.token());
        if (operation == ConnectionPolicy.Operation.REPORT_UPLOAD) {
            request.header("X-Civia-Account", principal.userId());
            request.header("X-Civia-Installation", scope.pairing().installationId());
        }
        if (operation == ConnectionPolicy.Operation.LOGIN) request.header("X-Session-Mode", "bearer");
        if (operation == ConnectionPolicy.Operation.REPORT_UPLOAD || operation == ConnectionPolicy.Operation.AGENT) {
            String key = call.getString("idempotencyKey", "");
            ConnectionPolicy.require(key.matches("[a-zA-Z0-9_-]{8,128}"));
            request.header("Idempotency-Key", key);
        }
        RequestBody body = null;
        if (operation == ConnectionPolicy.Operation.LOGOUT) body = RequestBody.create(new byte[0], null);
        else if (operation == ConnectionPolicy.Operation.REPORT_UPLOAD) body = multipart(call.getObject("multipart"));
        else if (operation == ConnectionPolicy.Operation.LOGIN || operation == ConnectionPolicy.Operation.AGENT
                || operation == ConnectionPolicy.Operation.CONFIRM) {
            String json = call.getString("json", "");
            ConnectionPolicy.require(!json.isEmpty() && json.length() <= 8192);
            body = RequestBody.create(json, JSON);
        }
        return request.method(method, body).build();
    }

    private static RequestBody multipart(JSObject input) throws Exception {
        if (input == null) throw new IllegalArgumentException();
        var builder = new MultipartBody.Builder().setType(MultipartBody.FORM);
        for (String field : new String[] { "title", "description", "latitude", "longitude" }) {
            String value = input.getString(field);
            ConnectionPolicy.require(value.length() <= 8192);
            builder.addFormDataPart(field, value);
        }
        addMedia(builder, "photo", input.getJSONObject("photo"));
        if (input.has("audio")) addMedia(builder, "audio", input.getJSONObject("audio"));
        return builder.build();
    }

    private static void addMedia(MultipartBody.Builder builder, String field, JSONObject input) throws Exception {
        String type = input.getString("type");
        String name = "photo".equals(field) ? switch (type) {
            case "image/jpeg" -> "foto.jpg";
            case "image/png" -> "foto.png";
            case "image/webp" -> "foto.webp";
            default -> throw new IllegalArgumentException();
        } : switch (type) {
            case "audio/wav", "audio/x-wav" -> "voz.wav";
            case "audio/mpeg", "audio/mp3" -> "voz.mp3";
            case "audio/ogg" -> "voz.ogg";
            case "audio/webm" -> "voz.webm";
            case "audio/mp4", "audio/m4a" -> "voz.m4a";
            default -> throw new IllegalArgumentException();
        };
        builder.addFormDataPart(field, name, RequestBody.create(media(input.getString("base64")), MediaType.get(type)));
    }

    private static byte[] media(String base64) {
        ConnectionPolicy.require(base64 != null && !base64.isEmpty() && base64.length() <= MAX_ENCODED_MEDIA);
        byte[] bytes = Base64.decode(base64, Base64.NO_WRAP);
        ConnectionPolicy.require(bytes.length > 0 && bytes.length <= MAX_MEDIA);
        return bytes;
    }

    private interface Work { void run(CiviaTransport.Cancellation cancellation) throws Exception; }

    private void submit(PluginCall call, Work work) {
        String requestId = call.getString("requestId", "");
        if (!requestId.matches("[a-zA-Z0-9_-]{8,80}")) { call.reject("Solicitud inválida.", "invalid"); return; }
        var cancellation = new CiviaTransport.Cancellation();
        if (operations.putIfAbsent(requestId, cancellation) != null) { call.reject("Solicitud inválida.", "invalid"); return; }
        try {
            workers.execute(() -> {
                try {
                    if (cancellation.cancelled()) throw new StaleStateException();
                    work.run(cancellation);
                } catch (CiviaTransport.IdentityException error) {
                    call.reject("La identidad del servidor no coincide con el emparejamiento.", "identity");
                } catch (IllegalArgumentException error) {
                    call.reject("Revisa los datos e intenta nuevamente.", "invalid");
                } catch (StaleStateException error) {
                    call.reject("Solicitud cancelada.", "cancelled");
                } catch (Exception error) {
                    call.reject("No fue posible conectar con CIVIA.", "unavailable");
                } finally { operations.remove(requestId, cancellation); }
            });
        } catch (java.util.concurrent.RejectedExecutionException error) {
            operations.remove(requestId, cancellation);
            call.reject("Intenta nuevamente en un momento.", "unavailable");
        }
    }
}
