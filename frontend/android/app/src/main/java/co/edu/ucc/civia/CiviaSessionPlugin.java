package co.edu.ucc.civia;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

@CapacitorPlugin(name = "CiviaSession")
public class CiviaSessionPlugin extends Plugin {
    private static final String KEYSTORE = "AndroidKeyStore";
    private static final String KEY_ALIAS = "civia.session.aes.v1";
    private static final String ENTRY = "session";
    private static final String TRANSFORMATION = "AES/GCM/NoPadding";
    private static final int IV_LENGTH = 12;

    private SharedPreferences preferences() {
        return getContext().getSharedPreferences("civia_session", Context.MODE_PRIVATE);
    }

    private synchronized SecretKey key() throws Exception {
        KeyStore store = KeyStore.getInstance(KEYSTORE);
        store.load(null);
        if (store.getKey(KEY_ALIAS, null) instanceof SecretKey existing) {
            return existing;
        }
        KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE);
        generator.init(new KeyGenParameterSpec.Builder(
            KEY_ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT
        ).setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build());
        return generator.generateKey();
    }

    @PluginMethod
    public void get(PluginCall call) {
        String value = preferences().getString(ENTRY, null);
        if (value == null) {
            call.resolve(new JSObject());
            return;
        }
        try {
            byte[] bytes = Base64.decode(value, Base64.NO_WRAP);
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, bytes, 0, IV_LENGTH));
            byte[] plaintext = cipher.doFinal(bytes, IV_LENGTH, bytes.length - IV_LENGTH);
            JSObject result = new JSObject();
            result.put("value", new String(plaintext, StandardCharsets.UTF_8));
            call.resolve(result);
        } catch (Exception ex) {
            // Missing or invalid keys require a new sign-in. Never log credentials or plaintext.
            preferences().edit().remove(ENTRY).commit();
            call.resolve(new JSObject());
        }
    }

    @PluginMethod
    public void set(PluginCall call) {
        String value = call.getString("value");
        if (value == null || value.isEmpty() || value.length() > 4096) {
            call.reject("Sesión móvil inválida.");
            return;
        }
        try {
            Cipher cipher = Cipher.getInstance(TRANSFORMATION);
            cipher.init(Cipher.ENCRYPT_MODE, key());
            byte[] iv = cipher.getIV();
            byte[] ciphertext = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
            byte[] file = Arrays.copyOf(iv, iv.length + ciphertext.length);
            System.arraycopy(ciphertext, 0, file, iv.length, ciphertext.length);
            if (iv.length != IV_LENGTH || !preferences().edit().putString(ENTRY, Base64.encodeToString(file, Base64.NO_WRAP)).commit()) {
                call.reject("No se pudo guardar la sesión móvil.");
                return;
            }
            call.resolve();
        } catch (Exception ex) {
            call.reject("No se pudo guardar la sesión móvil.");
        }
    }

    @PluginMethod
    public void clear(PluginCall call) {
        if (preferences().edit().remove(ENTRY).commit()) call.resolve();
        else call.reject("No se pudo cerrar la sesión móvil.");
    }
}
