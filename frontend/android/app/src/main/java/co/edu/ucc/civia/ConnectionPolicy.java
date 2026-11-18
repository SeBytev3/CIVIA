package co.edu.ucc.civia;

import java.net.URI;
import java.net.URLDecoder;
import java.io.UnsupportedEncodingException;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

final class ConnectionPolicy {
    private static final String UUID = "[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}";
    private static final Pattern UUID_PATTERN = Pattern.compile(UUID);
    private static final String REPORT = "/api/reports/" + UUID;
    private static final String TRACKING = "/api/reports/by-code/[A-Za-z0-9_-]{1,60}";

    enum Operation {
        PUBLIC, LOGIN, SESSION, LOGOUT, PRIVATE_READ, REPORT_UPLOAD, BINARY, CONFIRM, AGENT;

        boolean requiresSession() { return this != PUBLIC && this != LOGIN; }
    }

    record Pairing(String installationId, String origin, String pin) {
        Pairing {
            installationId = installation(installationId);
            origin = ConnectionPolicy.origin(origin);
            require(pin != null && pin.matches("[a-f0-9]{64}"));
        }

        Pairing at(String address) { return new Pairing(installationId, address, pin); }
    }

    static String installation(String value) {
        require(value != null && UUID_PATTERN.matcher(value).matches());
        return value.toLowerCase(Locale.ROOT);
    }

    static Pairing parsePairing(String input) {
        require(input != null && input.length() <= 1024);
        URI uri = URI.create(input.trim());
        require("civia".equals(uri.getScheme()) && "pair".equals(uri.getRawAuthority()) && "".equals(uri.getRawPath())
            && uri.getRawFragment() == null && uri.getRawQuery() != null);
        Map<String, String> fields = new HashMap<>();
        for (String field : uri.getRawQuery().split("&", -1)) {
            String[] pair = field.split("=", 2);
            require(pair.length == 2 && fields.put(pair[0], decode(pair[1])) == null);
        }
        require(fields.size() == 4 && "1".equals(fields.get("v")));
        return new Pairing(fields.get("id"), fields.get("origin"), fields.get("pin"));
    }

    private static String decode(String value) {
        try { return URLDecoder.decode(value, "UTF-8"); }
        catch (UnsupportedEncodingException error) { throw new AssertionError(error); }
    }

    static String origin(String value) {
        require(value != null && value.length() <= 350);
        URI uri = URI.create(value);
        String host = uri.getHost();
        int port = uri.getPort();
        require("https".equals(uri.getScheme()) && host != null && !host.contains("%") && port != 0 && port <= 65535
            && (uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath())) && uri.getRawQuery() == null
            && uri.getRawFragment() == null && uri.getRawUserInfo() == null);
        return "https://" + host.toLowerCase(Locale.ROOT) + (port == -1 || port == 443 ? "" : ":" + port);
    }

    static Operation operation(String method, String target) {
        require(target != null && target.length() <= 1024 && target.startsWith("/api/"));
        URI address = URI.create(target);
        require(address.getRawFragment() == null && address.getRawAuthority() == null);
        String path = address.getRawPath();
        String query = address.getRawQuery();
        if ("GET".equals(method)) {
            if (path.equals("/api/public/reports")) {
                checkQuery(query, "limit", "offset");
                return Operation.PUBLIC;
            }
            if (path.equals("/api/reports")) {
                checkQuery(query, "limit", "offset", "status", "category", "severity", "search", "q");
                return Operation.PRIVATE_READ;
            }
            require(query == null);
            if (path.equals("/api/public/reports/stats")) return Operation.PUBLIC;
            if (path.equals("/api/auth/session")) return Operation.SESSION;
            if (path.equals("/api/reports/stats") || path.matches(REPORT + "(/events)?")
                || path.matches(TRACKING + "(/events)?")) return Operation.PRIVATE_READ;
            if (path.matches(REPORT + "/(photo|audio)")) return Operation.BINARY;
        }
        require(query == null);
        if ("POST".equals(method)) {
            if (path.equals("/api/auth/login") || path.equals("/api/auth/register")) return Operation.LOGIN;
            if (path.equals("/api/auth/logout")) return Operation.LOGOUT;
            if (path.equals("/api/reports")) return Operation.REPORT_UPLOAD;
            if (path.equals("/api/agent/query")) return Operation.AGENT;
        }
        if ("PATCH".equals(method) && path.matches(REPORT + "/confirm")) return Operation.CONFIRM;
        throw new IllegalArgumentException();
    }

    private static void checkQuery(String query, String... allowed) {
        if (query == null) return;
        Set<String> seen = new HashSet<>();
        for (String item : query.split("&", -1)) {
            String[] pair = item.split("=", 2);
            require(pair.length == 2 && seen.add(pair[0]) && java.util.Arrays.asList(allowed).contains(pair[0]));
            require(!decode(pair[1]).chars().anyMatch(Character::isISOControl));
        }
    }

    static void require(boolean condition) {
        if (!condition) throw new IllegalArgumentException();
    }
}
