package co.edu.ucc.civia;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.Proxy;
import java.security.MessageDigest;
import java.security.cert.Certificate;
import java.security.cert.CertificateException;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLException;
import javax.net.ssl.X509TrustManager;
import okhttp3.Call;
import okhttp3.CookieJar;
import okhttp3.HttpUrl;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.ResponseBody;
import org.json.JSONObject;

final class CiviaTransport {
    record Reply(int status, String contentType, byte[] bytes) {}

    static final class IdentityException extends IOException { }

    static final class Cancellation {
        private Call current;
        private boolean cancelled;

        synchronized void track(Call call) {
            current = call;
            if (cancelled) call.cancel();
        }

        synchronized void cancel() {
            cancelled = true;
            if (current != null) current.cancel();
        }

        synchronized boolean cancelled() { return cancelled; }
    }

    private final ConnectionPolicy.Pairing pairing;
    private final OkHttpClient client;

    CiviaTransport(ConnectionPolicy.Pairing pairing) throws Exception {
        this.pairing = pairing;
        var trust = new CertificatePin(pairing.pin());
        var ssl = SSLContext.getInstance("TLS");
        ssl.init(null, new X509TrustManager[] { trust }, null);
        var authority = HttpUrl.get(pairing.origin());
        client = new OkHttpClient.Builder()
            .sslSocketFactory(ssl.getSocketFactory(), trust)
            .hostnameVerifier((host, session) -> {
                // The paired installation certificate is the server name even when DHCP changes its IP.
                try {
                    Certificate[] certificates = session.getPeerCertificates();
                    return host.equals(authority.host()) && certificates.length > 0
                        && certificates[0] instanceof X509Certificate leaf && trust.matches(leaf);
                } catch (Exception invalid) { return false; }
            })
            .cookieJar(CookieJar.NO_COOKIES)
            .proxy(Proxy.NO_PROXY)
            .followRedirects(false)
            .followSslRedirects(false)
            .retryOnConnectionFailure(false)
            .connectTimeout(4, TimeUnit.SECONDS)
            .readTimeout(38, TimeUnit.SECONDS)
            .writeTimeout(20, TimeUnit.SECONDS)
            .callTimeout(40, TimeUnit.SECONDS)
            .build();
    }

    Request.Builder request(String path) {
        return new Request.Builder().url(pairing.origin() + path).header("Cache-Control", "no-store");
    }

    void verify(Cancellation cancellation) throws Exception {
        var reply = exchange(request("/api/meta").header("Accept", "application/json").build(), cancellation, 4096, 5);
        if (reply.status >= 500) throw new IOException();
        try {
            if (reply.status != 200 || !reply.contentType.startsWith("application/json")) throw new IdentityException();
            var meta = new JSONObject(new String(reply.bytes, java.nio.charset.StandardCharsets.UTF_8));
            if (!Integer.valueOf(1).equals(meta.opt("protocol"))
                || !pairing.installationId().equals(ConnectionPolicy.installation(meta.getString("installation_id")))) {
                throw new IdentityException();
            }
        } catch (IllegalArgumentException | org.json.JSONException invalid) { throw new IdentityException(); }
    }

    Reply exchange(Request request, Cancellation cancellation, int limit, int seconds) throws IOException {
        Call call = client.newCall(request);
        call.timeout().timeout(seconds, TimeUnit.SECONDS);
        cancellation.track(call);
        try (var response = call.execute()) {
            if (response.isRedirect() || response.code() < 200 || response.code() >= 300) {
                return new Reply(response.code(), "", new byte[0]);
            }
            String type = response.header("Content-Type", "");
            return new Reply(response.code(), type, boundedBytes(response.body(), limit));
        } catch (SSLException invalid) { throw new IdentityException(); }
    }

    private static byte[] boundedBytes(ResponseBody body, int limit) throws IOException {
        if (body == null) return new byte[0];
        if (body.contentLength() > limit) throw new IOException();
        try (var stream = body.byteStream(); var out = new ByteArrayOutputStream()) {
            var buffer = new byte[8192];
            int count;
            while ((count = stream.read(buffer)) != -1) {
                if (out.size() + count > limit) throw new IOException();
                out.write(buffer, 0, count);
            }
            return out.toByteArray();
        }
    }

    private record CertificatePin(String hexadecimal) implements X509TrustManager {
        boolean matches(X509Certificate leaf) throws Exception {
            leaf.checkValidity();
            List<String> purposes = leaf.getExtendedKeyUsage();
            if (purposes != null && !purposes.contains("1.3.6.1.5.5.7.3.1")) return false;
            var expected = new byte[32];
            for (int i = 0; i < expected.length; i++) {
                expected[i] = (byte) Integer.parseInt(hexadecimal.substring(i * 2, i * 2 + 2), 16);
            }
            return MessageDigest.isEqual(expected, MessageDigest.getInstance("SHA-256").digest(leaf.getEncoded()));
        }

        @Override public void checkServerTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            try {
                if (chain != null && chain.length > 0 && matches(chain[0])) return;
            } catch (Exception invalid) { throw new CertificateException("CIVIA certificate does not match", invalid); }
            throw new CertificateException("CIVIA certificate does not match");
        }

        @Override public void checkClientTrusted(X509Certificate[] chain, String authType) throws CertificateException {
            throw new CertificateException("Client certificates are unsupported");
        }

        @Override public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
    }
}
