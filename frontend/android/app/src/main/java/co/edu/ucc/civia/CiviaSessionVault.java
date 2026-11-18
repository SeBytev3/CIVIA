package co.edu.ucc.civia;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.text.ParsePosition;
import java.text.SimpleDateFormat;
import java.util.Arrays;
import java.util.Locale;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

final class CiviaSessionVault {
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String KEY_ALIAS = "civia.session.aes.v2";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int IV_LENGTH = 12;
    private final SharedPreferences preferences;

    record Session(String userId, String token, String visible) {}

    CiviaSessionVault(Context context) {
        preferences = context.getSharedPreferences("civia_paired_sessions", Context.MODE_PRIVATE);
    }

    static Session validate(JSONObject response, String token) throws Exception {
        var user = response.getJSONObject("user");
        ConnectionPolicy.require("CITIZEN".equals(user.getString("role")) && user.getBoolean("active"));
        String userId = ConnectionPolicy.installation(user.getString("id"));
        ConnectionPolicy.require(token.matches("[A-Za-z0-9_-]{43,128}"));
        String expiration = response.getString("expires_at").replaceFirst("\\.\\d+(?=Z|[+-]\\d{2}:\\d{2}$)", "");
        var format = new SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.ROOT);
        format.setLenient(false);
        var offset = new ParsePosition(0);
        var expires = format.parse(expiration, offset);
        ConnectionPolicy.require(expires != null && offset.getIndex() == expiration.length() && expires.getTime() > System.currentTimeMillis());
        response.remove("token");
        response.remove("csrf_token");
        return new Session(userId, token, response.toString());
    }

    private SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance(KEYSTORE);
        store.load(null);
        if (store.getKey(KEY_ALIAS, null) instanceof SecretKey existing) return existing;
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        generator.init(new KeyGenParameterSpec.Builder(KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build());
        return generator.generateKey();
    }

    private String entry(ConnectionPolicy.Pairing pairing) { return pairing.installationId() + ":" + pairing.pin(); }

    Session get(ConnectionPolicy.Pairing pairing) {
        String entry = entry(pairing);
        String value = preferences.getString(entry, null);
        if (value == null) return null;
        try {
            byte[] bytes = Base64.decode(value, Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, bytes, 0, IV_LENGTH));
            cipher.updateAAD(entry.getBytes(StandardCharsets.UTF_8));
            byte[] plaintext = cipher.doFinal(bytes, IV_LENGTH, bytes.length - IV_LENGTH);
            JSONObject session = new JSONObject(new String(plaintext, StandardCharsets.UTF_8));
            return validate(session, session.getString("token"));
        } catch (Exception invalid) {
            preferences.edit().remove(entry).commit();
            return null;
        }
    }

    void set(ConnectionPolicy.Pairing pairing, Session session) throws Exception {
        String entry = entry(pairing);
        byte[] value = new JSONObject(session.visible()).put("token", session.token()).toString().getBytes(StandardCharsets.UTF_8);
        Cipher cipher = Cipher.getInstance(TRANSFORMATION);
        cipher.init(Cipher.ENCRYPT_MODE, key());
        cipher.updateAAD(entry.getBytes(StandardCharsets.UTF_8));
        byte[] iv = cipher.getIV();
        byte[] ciphertext = cipher.doFinal(value);
        byte[] file = Arrays.copyOf(iv, iv.length + ciphertext.length);
        System.arraycopy(ciphertext, 0, file, iv.length, ciphertext.length);
        if (iv.length != IV_LENGTH || !preferences.edit().putString(entry, Base64.encodeToString(file, Base64.NO_WRAP)).commit()) {
            throw new IllegalStateException();
        }
    }

    void clear(ConnectionPolicy.Pairing pairing) {
        if (!preferences.edit().remove(entry(pairing)).commit()) throw new IllegalStateException();
    }
}
