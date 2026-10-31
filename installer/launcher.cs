// PoE Tracker.exe: starts the tracker with the Python that the installer put
// next to it (python\pythonw.exe -m poetracker). No console window.
//   --console   show a window with the tracker's messages (stays open after it exits)
//   --dev       developer mode (only on a developer copy, or with dev_mode: true in settings.yaml)
// Any other arguments are passed on to "python -m poetracker run".
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("PoE Tracker")]
[assembly: AssemblyProduct("PoE Tracker")]
[assembly: AssemblyDescription("Path of Exile play tracker")]
[assembly: AssemblyCompany("deweesa1")]

static class Launcher
{
    static string Quote(string a)
    {
        return a.IndexOfAny(new[] { ' ', '"', '\t' }) < 0 ? a : "\"" + a.Replace("\"", "\\\"") + "\"";
    }

    [STAThread]
    static int Main(string[] args)
    {
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        bool console = args.Contains("--console");
        string[] rest = args.Where(a => a != "--console").ToArray();
        string pyDir = Path.Combine(dir, "python");
        string py = Path.Combine(pyDir, console ? "python.exe" : "pythonw.exe");
        string app = Path.Combine(dir, "app");
        if (!File.Exists(py) || !Directory.Exists(Path.Combine(app, "poetracker")))
        {
            MessageBox.Show("Part of PoE Tracker is missing.\n\nRun PoE Tracker Setup again (your data is kept).",
                            "PoE Tracker", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        string runArgs = "-m poetracker run" + (rest.Length > 0 ? " " + string.Join(" ", rest.Select(Quote)) : "");
        ProcessStartInfo psi;
        if (console)
        {
            // a console that stays open afterwards, so errors can be read
            psi = new ProcessStartInfo("cmd.exe",
                "/k \"title PoE Tracker" + (rest.Contains("--dev") ? " (dev)" : "") + " & " + Quote(py) + " " + runArgs + "\"");
            psi.UseShellExecute = true;
        }
        else
        {
            psi = new ProcessStartInfo(py, runArgs);
            psi.UseShellExecute = false;
        }
        psi.WorkingDirectory = app;
        try
        {
            Process.Start(psi);
        }
        catch (Exception e)
        {
            MessageBox.Show("Couldn't start PoE Tracker:\n\n" + e.Message, "PoE Tracker",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        return 0;
    }
}
