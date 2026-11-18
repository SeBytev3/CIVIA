package co.edu.ucc.civia;

import static org.junit.Assert.*;

import android.content.Context;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import androidx.test.core.app.ActivityScenario;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class AndroidConnectionTest {
    private static final String INSTALLATION = "d5764f06-efae-428e-8431-6713a26be626";

    @Test public void webViewAllowsOnlyTheRestrictedNativeTransport() {
        try (var scenario = ActivityScenario.launch(MainActivity.class)) {
            scenario.onActivity(activity -> {
                assertEquals("co.edu.ucc.civia", activity.getPackageName());
                var generic = activity.getBridge().getPlugin("CapacitorHttp");
                assertEquals(MainActivity.DisabledHttp.class, generic.getPluginClass());
                assertFalse(activity.getBridge().getConfig().isLoggingEnabled());
                assertTrue(generic.getMethods().stream().noneMatch(method ->
                    "request".equals(method.getName()) || "get".equals(method.getName())));
                assertEquals(CiviaConnectionPlugin.class, activity.getBridge().getPlugin("CiviaConnection").getPluginClass());
                assertFalse(android.security.NetworkSecurityPolicy.getInstance().isCleartextTrafficPermitted());
            });
        }
    }

    @Test public void bundledLoopbackPreservesTheLegacyStorageOriginAndSecureFeatures() throws Exception {
        try (var scenario = ActivityScenario.launch(MainActivity.class)) {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(20);
            do {
                var result = new AtomicReference<String>();
                var returned = new CountDownLatch(1);
                scenario.onActivity(activity -> activity.getBridge().getWebView().evaluateJavascript(
                    "location.origin === 'http://localhost' && isSecureContext && !!navigator.mediaDevices && !!indexedDB && !!document.querySelector('h1')",
                    value -> { result.set(value); returned.countDown(); }
                ));
                if (returned.await(2, TimeUnit.SECONDS) && "true".equals(result.get())) return;
                Thread.sleep(300);
            } while (System.nanoTime() < deadline);
            fail("The bundled UI did not load in its secure loopback storage origin");
        }
    }

    @Test public void nsdResolvesTheVersionedCiviaService() throws Exception {
        var instrument = InstrumentationRegistry.getInstrumentation();
        Context context = instrument.getTargetContext();
        var nsd = context.getSystemService(NsdManager.class);
        var service = new NsdServiceInfo();
        service.setServiceName("CIVIA - Prueba instrumentada");
        service.setServiceType(CiviaDiscovery.TYPE);
        service.setPort(15451);
        service.setAttribute("v", "1");
        service.setAttribute("scheme", "https");
        service.setAttribute("id", INSTALLATION);
        var registration = new CountDownLatch(1);
        var discovered = new CountDownLatch(1);
        var listener = new NsdManager.RegistrationListener() {
            @Override public void onRegistrationFailed(NsdServiceInfo info, int error) { }
            @Override public void onUnregistrationFailed(NsdServiceInfo info, int error) { }
            @Override public void onServiceRegistered(NsdServiceInfo info) { registration.countDown(); }
            @Override public void onServiceUnregistered(NsdServiceInfo info) { }
        };
        var discovery = new CiviaDiscovery(context, event -> {
            var candidates = event.optJSONArray("candidates");
            for (int i = 0; candidates != null && i < candidates.length(); i++) {
                JSONObject candidate = candidates.optJSONObject(i);
                if (candidate != null && INSTALLATION.equals(candidate.optString("installationId"))) {
                    var origins = candidate.optJSONArray("origins");
                    if (origins != null && origins.optString(0).matches("https://.+:15451")) discovered.countDown();
                }
            }
        }, () -> { });
        try {
            instrument.runOnMainSync(discovery::start);
            nsd.registerService(service, NsdManager.PROTOCOL_DNS_SD, listener);
            assertTrue("Could not advertise test DNS-SD service", registration.await(12, TimeUnit.SECONDS));
            assertTrue("CIVIA service did not resolve to an HTTPS endpoint", discovered.await(15, TimeUnit.SECONDS));
        } finally {
            instrument.runOnMainSync(discovery::stop);
            try { nsd.unregisterService(listener); } catch (IllegalArgumentException ignored) { }
        }
    }
}
