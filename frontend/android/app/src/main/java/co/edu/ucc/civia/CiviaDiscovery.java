package co.edu.ucc.civia;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.LinkProperties;
import android.net.Network;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.ext.SdkExtensions;
import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

final class CiviaDiscovery {
    static final String TYPE = "_civia._tcp.";
    private static final int MAX_SERVICES = 16;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final NsdManager nsd;
    private final WifiManager wifi;
    private final ConnectivityManager connectivity;
    private final Consumer<JSObject> publish;
    private final Runnable networkChanged;
    private final Map<String, NsdManager.ServiceInfoCallback> subscriptions = new LinkedHashMap<>();
    private final Map<String, NsdServiceInfo> resolved = new LinkedHashMap<>();
    private final Map<String, Boolean> present = new LinkedHashMap<>();
    private final ArrayDeque<NsdServiceInfo> pending = new ArrayDeque<>();
    private NsdManager.DiscoveryListener discovery;
    private WifiManager.MulticastLock multicast;
    private boolean watchingNetwork;
    private boolean resolving;
    private boolean requested;

    private final Runnable restart = () -> {
        if (!requested) return;
        stopDiscovery();
        startDiscovery();
        signalNetworkChange();
    };

    private final ConnectivityManager.NetworkCallback networkCallback = new ConnectivityManager.NetworkCallback() {
        @Override public void onAvailable(Network network) { changed(); }
        @Override public void onLost(Network network) { changed(); }
        @Override public void onLinkPropertiesChanged(Network network, LinkProperties properties) { changed(); }
        private void changed() {
            handler.removeCallbacks(restart);
            handler.postDelayed(restart, 300);
        }
    };

    CiviaDiscovery(Context context, Consumer<JSObject> publish, Runnable networkChanged) {
        nsd = context.getSystemService(NsdManager.class);
        wifi = context.getApplicationContext().getSystemService(WifiManager.class);
        connectivity = context.getSystemService(ConnectivityManager.class);
        this.publish = publish;
        this.networkChanged = networkChanged;
    }

    private void signalNetworkChange() { networkChanged.run(); }

    void start() {
        requested = true;
        if (!watchingNetwork && connectivity != null) {
            try {
                connectivity.registerDefaultNetworkCallback(networkCallback);
                watchingNetwork = true;
            } catch (RuntimeException ignored) { }
        }
        startDiscovery();
    }

    void stop() {
        requested = false;
        handler.removeCallbacks(restart);
        stopDiscovery();
        if (watchingNetwork) {
            watchingNetwork = false;
            try { connectivity.unregisterNetworkCallback(networkCallback); }
            catch (IllegalArgumentException ignored) { }
        }
    }

    private static boolean needsMulticastLock() {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU
            || SdkExtensions.getExtensionVersion(Build.VERSION_CODES.TIRAMISU) < 7;
    }

    private void startDiscovery() {
        if (discovery != null) return;
        if (nsd == null) { emit("unavailable"); return; }
        NsdManager.DiscoveryListener listener = new NsdManager.DiscoveryListener() {
            @Override public void onDiscoveryStarted(String type) { }
            @Override public void onStartDiscoveryFailed(String type, int error) { handler.post(() -> failed(this)); }
            @Override public void onDiscoveryStopped(String type) { }
            @Override public void onStopDiscoveryFailed(String type, int error) { }
            @Override public void onServiceFound(NsdServiceInfo service) { handler.post(() -> { if (discovery == this) found(service); }); }
            @Override public void onServiceLost(NsdServiceInfo service) { handler.post(() -> { if (discovery == this) lost(service); }); }
        };
        discovery = listener;
        try {
            if (wifi != null && needsMulticastLock() && wifi.isWifiEnabled()) {
                multicast = wifi.createMulticastLock("civia-discovery");
                multicast.setReferenceCounted(false);
                multicast.acquire();
            }
            nsd.discoverServices(TYPE, NsdManager.PROTOCOL_DNS_SD, listener);
            emit("searching");
        } catch (RuntimeException error) { failed(listener); }
    }

    private void failed(NsdManager.DiscoveryListener listener) {
        if (discovery != listener) return;
        stopDiscovery();
        emit("unavailable");
    }

    private void stopDiscovery() {
        NsdManager.DiscoveryListener old = discovery;
        discovery = null;
        if (old != null) {
            try { nsd.stopServiceDiscovery(old); }
            catch (RuntimeException ignored) { }
        }
        if (Build.VERSION.SDK_INT >= 34) {
            for (var callback : subscriptions.values()) unregister(callback);
        }
        subscriptions.clear();
        resolved.clear();
        present.clear();
        pending.clear();
        // Android 24–33 lacks a cancellation API. The in-flight callback is ignored after a restart.
        if (multicast != null) {
            if (multicast.isHeld()) multicast.release();
            multicast = null;
        }
    }

    private static String key(NsdServiceInfo service) {
        Network network = Build.VERSION.SDK_INT >= 33 ? service.getNetwork() : null;
        return service.getServiceName() + "@" + network;
    }

    private void found(NsdServiceInfo service) {
        String type = service.getServiceType();
        if (!(TYPE.equals(type) || "_civia._tcp".equals(type))) return;
        String key = key(service);
        if (present.containsKey(key) || present.size() >= MAX_SERVICES) return;
        present.put(key, true);
        if (Build.VERSION.SDK_INT >= 34) subscribe(key, service);
        else {
            pending.add(service);
            resolveNext();
        }
    }

    @android.annotation.TargetApi(34)
    private void subscribe(String key, NsdServiceInfo service) {
        var callback = new NsdManager.ServiceInfoCallback() {
            @Override public void onServiceInfoCallbackRegistrationFailed(int error) {
                if (subscriptions.remove(key, this)) {
                    present.remove(key);
                    resolved.remove(key);
                    emit("searching");
                }
            }
            @Override public void onServiceUpdated(NsdServiceInfo info) {
                if (subscriptions.get(key) == this) {
                    resolved.put(key, info);
                    emit("searching");
                }
            }
            @Override public void onServiceLost() {
                if (subscriptions.get(key) == this) {
                    resolved.remove(key);
                    emit("searching");
                }
            }
            @Override public void onServiceInfoCallbackUnregistered() { }
        };
        subscriptions.put(key, callback);
        try { nsd.registerServiceInfoCallback(service, handler::post, callback); }
        catch (RuntimeException error) { callback.onServiceInfoCallbackRegistrationFailed(NsdManager.FAILURE_BAD_PARAMETERS); }
    }

    @android.annotation.TargetApi(34)
    private void unregister(NsdManager.ServiceInfoCallback callback) {
        try { nsd.unregisterServiceInfoCallback(callback); }
        catch (RuntimeException ignored) { }
    }

    private void lost(NsdServiceInfo service) {
        String key = key(service);
        present.remove(key);
        if (Build.VERSION.SDK_INT >= 34) {
            var callback = subscriptions.remove(key);
            if (callback != null) unregister(callback);
        }
        pending.removeIf(item -> key(item).equals(key));
        resolved.remove(key);
        emit("searching");
    }

    @SuppressWarnings("deprecation")
    private void resolveNext() {
        if (resolving || pending.isEmpty() || discovery == null) return;
        var scope = discovery;
        var next = pending.removeFirst();
        String key = key(next);
        resolving = true;
        var listener = new NsdManager.ResolveListener() {
            @Override public void onResolveFailed(NsdServiceInfo info, int error) { handler.post(() -> done(null)); }
            @Override public void onServiceResolved(NsdServiceInfo info) { handler.post(() -> done(info)); }
            private void done(NsdServiceInfo info) {
                resolving = false;
                if (scope == discovery && present.containsKey(key)) {
                    if (info == null) present.remove(key);
                    else resolved.put(key, info);
                    emit("searching");
                }
                resolveNext();
            }
        };
        try { nsd.resolveService(next, listener); }
        catch (RuntimeException exception) { listener.onResolveFailed(next, 0); }
    }

    private void emit(String state) {
        JSArray candidates = new JSArray();
        for (NsdServiceInfo service : resolved.values()) {
            try {
                var attributes = service.getAttributes();
                if (!"1".equals(text(attributes.get("v"))) || !"https".equals(text(attributes.get("scheme")))) continue;
                String installation = ConnectionPolicy.installation(text(attributes.get("id")));
                int port = service.getPort();
                if (port <= 0 || port > 65535) continue;
                JSArray origins = new JSArray();
                for (InetAddress address : addresses(service)) {
                    if (address.isLinkLocalAddress() || address.isLoopbackAddress() || address.isAnyLocalAddress() || address.isMulticastAddress()) continue;
                    String host = address.getHostAddress();
                    if (host.contains(":")) host = "[" + host.split("%", 2)[0] + "]";
                    origins.put(ConnectionPolicy.origin("https://" + host + ":" + port));
                }
                if (origins.length() > 0) candidates.put(new JSObject()
                    .put("name", service.getServiceName()).put("installationId", installation).put("origins", origins));
            } catch (IllegalArgumentException ignored) { }
        }
        publish.accept(new JSObject().put("state", state).put("candidates", candidates));
    }

    @SuppressWarnings("deprecation")
    private static List<InetAddress> addresses(NsdServiceInfo service) {
        if (Build.VERSION.SDK_INT >= 34) return service.getHostAddresses();
        InetAddress host = service.getHost();
        return host == null ? java.util.Collections.emptyList() : java.util.Collections.singletonList(host);
    }

    private static String text(byte[] bytes) {
        return bytes == null ? "" : new String(bytes, StandardCharsets.US_ASCII);
    }
}
