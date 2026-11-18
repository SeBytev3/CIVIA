package co.edu.ucc.civia;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.Plugin;
import com.getcapacitor.annotation.CapacitorPlugin;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(CiviaConnectionPlugin.class);
        registerPlugin(CiviaAudioPlugin.class);
        registerPlugin(DisabledHttp.class);
        super.onCreate(savedInstanceState);
    }

    @CapacitorPlugin(name = "CapacitorHttp")
    public static final class DisabledHttp extends Plugin {
        @Override public void load() {
            // Capacitor registers this bridge even when its fetch patch is disabled.
            getBridge().getWebView().removeJavascriptInterface("CapacitorHttpAndroidInterface");
        }
    }
}
