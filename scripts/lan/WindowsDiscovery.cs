using System;
using System.Net;
using System.Runtime.InteropServices;
using System.Threading;

public sealed class CiviaDiscovery : IDisposable
{
    private const uint Pending = 9506;
    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate void Completion(uint status, IntPtr context, IntPtr instance);

    [StructLayout(LayoutKind.Sequential)]
    private struct Request
    {
        public uint Version, InterfaceIndex;
        public IntPtr Instance;
        public Completion Callback;
        public IntPtr Context, Credentials;
        public int Unicast;
    }

    [DllImport("dnsapi.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr DnsServiceConstructInstance(
        string service, string host, ref uint ipv4, IntPtr ipv6, ushort port, ushort priority,
        ushort weight, uint propertyCount,
        [MarshalAs(UnmanagedType.LPArray, ArraySubType = UnmanagedType.LPWStr)] string[] keys,
        [MarshalAs(UnmanagedType.LPArray, ArraySubType = UnmanagedType.LPWStr)] string[] values);

    [DllImport("dnsapi.dll")]
    private static extern uint DnsServiceRegister(ref Request request, IntPtr cancel);
    [DllImport("dnsapi.dll")]
    private static extern uint DnsServiceDeRegister(ref Request request, IntPtr cancel);
    [DllImport("dnsapi.dll")]
    private static extern void DnsServiceFreeInstance(IntPtr instance);

    private readonly ManualResetEvent complete = new ManualResetEvent(false);
    private Request request;
    private uint code;
    private bool active;

    public CiviaDiscovery(uint interfaceIndex, string address, string name, ushort port, Guid identity)
    {
        if (interfaceIndex == 0) throw new ArgumentException("Se requiere una interfaz LAN.");
        uint ipv4 = BitConverter.ToUInt32(IPAddress.Parse(address).GetAddressBytes(), 0);
        string service = "CIVIA - Servidor local " + identity.ToString("N").Substring(0, 8) + "._civia._tcp.local.";
        request = new Request {
            Version = 1, InterfaceIndex = interfaceIndex, Callback = OnComplete,
            Instance = DnsServiceConstructInstance(service, name + ".", ref ipv4, IntPtr.Zero, port, 0, 0, 3,
                new[] { "v", "id", "scheme" }, new[] { "1", identity.ToString(), "https" })
        };
        if (request.Instance == IntPtr.Zero) throw new InvalidOperationException("No se pudo construir el anuncio DNS-SD.");
        try {
            WaitForCompletion(DnsServiceRegister(ref request, IntPtr.Zero));
            active = true;
        } catch {
            DnsServiceFreeInstance(request.Instance);
            throw;
        }
    }

    private void OnComplete(uint status, IntPtr context, IntPtr instance)
    {
        code = status;
        if (instance != IntPtr.Zero && instance != request.Instance) DnsServiceFreeInstance(instance);
        complete.Set();
    }

    private void WaitForCompletion(uint result)
    {
        if (result != Pending) throw new InvalidOperationException("DNS-SD no disponible (" + result + ").");
        if (!complete.WaitOne(TimeSpan.FromSeconds(8))) throw new TimeoutException("DNS-SD sin respuesta.");
        if (code != 0) throw new InvalidOperationException("DNS-SD no disponible (" + code + ").");
    }

    public void Dispose()
    {
        if (!active) return;
        active = false;
        complete.Reset();
        try { WaitForCompletion(DnsServiceDeRegister(ref request, IntPtr.Zero)); }
        finally { DnsServiceFreeInstance(request.Instance); }
    }
}
