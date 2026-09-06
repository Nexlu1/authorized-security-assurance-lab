using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace McrToolingPreview;

internal static class ConsoleWindowPolicy
{
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool FreeConsole();

    [ModuleInitializer]
    internal static void Initialize()
    {
        if (!OperatingSystem.IsWindows()) return;
        if (Environment.GetCommandLineArgs().Any(a => a.Equals("--self-test", StringComparison.OrdinalIgnoreCase))) return;
        _ = FreeConsole();
    }
}
