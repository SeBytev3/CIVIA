package co.edu.ucc.civia;

import static org.junit.Assert.*;

import org.junit.Test;

public class ConnectionPolicyTest {
    private static final String INSTALLATION = "d5764f06-efae-428e-8431-6713a26be626";
    private static final String PIN = "7d9e5505300722b7a404fda3eb1f2bd4f1263c8660729cd131974dabfe827303";
    private static final String PAIRING = "civia://pair?v=1&id=" + INSTALLATION
        + "&origin=https%3A%2F%2F192.168.1.44%3A5443&pin=" + PIN;

    @Test public void pairingRequiresTlsAndRejectsAmbiguousInputs() {
        var pair = ConnectionPolicy.parsePairing(PAIRING);
        assertEquals(INSTALLATION, pair.installationId());
        assertEquals("https://192.168.1.44:5443", pair.origin());
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.parsePairing(PAIRING + "&v=1"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.parsePairing(PAIRING.replace("https", "http")));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.parsePairing(PAIRING.replace("5443", "5443%2Fapi")));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.parsePairing(PAIRING.replace(PIN, "bad")));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.origin("https://example.org@127.0.0.1:443"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.origin("https://192.168.1.7:5443/../"));
    }

    @Test public void onlyKnownCitizenRoutesAndMethodsAreAdmitted() {
        assertEquals(ConnectionPolicy.Operation.REPORT_UPLOAD, ConnectionPolicy.operation("POST", "/api/reports"));
        assertEquals(ConnectionPolicy.Operation.BINARY, ConnectionPolicy.operation("GET", "/api/reports/" + INSTALLATION + "/photo"));
        assertEquals(ConnectionPolicy.Operation.PRIVATE_READ, ConnectionPolicy.operation("GET", "/api/reports?limit=10&offset=0"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.operation("GET", "https://example.org/api/reports"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.operation("POST", "/api/admin/fault-injection"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.operation("POST", "/api/reports/" + INSTALLATION + "/status"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.operation("POST", "/api/reports?limit=10"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.operation("GET", "/api/reports/../auth/session"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.operation("GET", "/api/reports/by-code/%2e%2e%2fauth"));
        assertThrows(IllegalArgumentException.class, () -> ConnectionPolicy.operation("GET", "/api/auth/session?token=a"));
    }
}
