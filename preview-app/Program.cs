using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;

namespace McrToolingPreview;

internal sealed class RuntimeConfig
{
    public string schema { get; set; } = "";
    public string status { get; set; } = "";
    public string engine_path { get; set; } = "";
    public string engine_sha256 { get; set; } = "";
    public string qpdf_path { get; set; } = "";
    public string qpdf_sha256 { get; set; } = "";
    public string pdfcpu_path { get; set; } = "";
    public string pdfcpu_sha256 { get; set; } = "";
}

internal readonly record struct RunResult(int ExitCode, string StdOut, string StdErr);

internal static class ProcessRunner
{
    public static async Task<RunResult> RunAsync(string exe, IEnumerable<string> args)
    {
        var psi = new ProcessStartInfo(exe) { UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true, CreateNoWindow = true };
        foreach (var a in args) psi.ArgumentList.Add(a);
        using var p = Process.Start(psi) ?? throw new InvalidOperationException($"Could not start {exe}");
        var stdout = p.StandardOutput.ReadToEndAsync();
        var stderr = p.StandardError.ReadToEndAsync();
        await p.WaitForExitAsync();
        return new RunResult(p.ExitCode, await stdout, await stderr);
    }
}

internal static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        if (args.Any(a => a.Equals("--self-test", StringComparison.OrdinalIgnoreCase)))
        {
            Environment.ExitCode = SelfTest();
            return;
        }
        ApplicationConfiguration.Initialize();
        Application.Run(new MainForm());
    }

    internal static string Root => AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);

    internal static RuntimeConfig LoadConfig()
    {
        var path = Path.Combine(Root, "control", "runtime.json");
        if (!File.Exists(path)) throw new FileNotFoundException("Missing controlled runtime manifest", path);
        return JsonSerializer.Deserialize<RuntimeConfig>(File.ReadAllText(path), new JsonSerializerOptions { PropertyNameCaseInsensitive = true })
               ?? throw new InvalidDataException("runtime.json could not be parsed");
    }

    internal static string Full(string relative) => Path.GetFullPath(Path.Combine(Root, relative.Replace('/', Path.DirectorySeparatorChar)));

    internal static string Sha256(string path)
    {
        using var s = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(s)).ToLowerInvariant();
    }

    private static int SelfTest()
    {
        try
        {
            var c = LoadConfig();
            var checks = new[] { ("mcr-ingest", c.engine_path, c.engine_sha256), ("qpdf", c.qpdf_path, c.qpdf_sha256), ("pdfcpu", c.pdfcpu_path, c.pdfcpu_sha256) };
            foreach (var (name, rel, expected) in checks)
            {
                var p = Full(rel);
                if (!File.Exists(p)) throw new FileNotFoundException($"Missing {name}", p);
                var actual = Sha256(p);
                if (!actual.Equals(expected, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException($"{name} SHA-256 mismatch: expected {expected}, actual {actual}");
                Console.WriteLine($"PASS {name} sha256={actual}");
            }
            var engine = ProcessRunner.RunAsync(Full(c.engine_path), Array.Empty<string>()).GetAwaiter().GetResult();
            if (engine.ExitCode != 0) throw new InvalidOperationException($"mcr-ingest launch failed: {engine.StdErr}");
            var qpdf = ProcessRunner.RunAsync(Full(c.qpdf_path), new[] { "--version" }).GetAwaiter().GetResult();
            if (qpdf.ExitCode != 0) throw new InvalidOperationException($"qpdf launch failed: {qpdf.StdErr}");
            var pdfcpu = ProcessRunner.RunAsync(Full(c.pdfcpu_path), new[] { "version" }).GetAwaiter().GetResult();
            if (pdfcpu.ExitCode != 0) throw new InvalidOperationException($"pdfcpu launch failed: {pdfcpu.StdErr}");
            Console.WriteLine("PASS engineering-preview runtime self-check");
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine("FAIL " + ex);
            return 2;
        }
    }
}

internal sealed class MainForm : Form
{
    private readonly RuntimeConfig cfg;
    private readonly TextBox workspace = new() { Dock = DockStyle.Fill };
    private readonly ListView files = new() { Dock = DockStyle.Fill, View = View.Details, FullRowSelect = true, GridLines = true, HideSelection = false };
    private readonly RichTextBox log = new() { Dock = DockStyle.Fill, ReadOnly = true, Font = new Font("Consolas", 9F), BackColor = Color.White };
    private readonly Label state = new() { AutoSize = true, Text = "Ready" };
    private readonly Button run = new() { Text = "Run selected / all", AutoSize = true };

    public MainForm()
    {
        try { cfg = Program.LoadConfig(); }
        catch (Exception ex) { MessageBox.Show(ex.Message, "MCR Tooling Preview", MessageBoxButtons.OK, MessageBoxIcon.Error); cfg = new RuntimeConfig(); }

        Text = "MCR Tooling — Engineering Preview R2.4";
        Width = 1180; Height = 780; MinimumSize = new Size(900, 620); StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9F);

        var header = new Panel { Dock = DockStyle.Top, Height = 94, Padding = new Padding(18, 14, 18, 8), BackColor = Color.FromArgb(32, 34, 37) };
        var title = new Label { Text = "MCR Tooling — Engineering Preview", ForeColor = Color.White, Font = new Font("Segoe UI Semibold", 18F), AutoSize = true, Location = new Point(18, 12) };
        var sub = new Label { Text = "Working R2.4 ingestion engine • 57/57 controlled hostile behaviours functionally exercised • Frozen MCR R59 is not modified", ForeColor = Color.Gainsboro, AutoSize = true, Location = new Point(20, 53) };
        header.Controls.Add(title); header.Controls.Add(sub);

        var top = new TableLayoutPanel { Dock = DockStyle.Top, Height = 92, Padding = new Padding(12, 10, 12, 4), ColumnCount = 3, RowCount = 2 };
        top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 100)); top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120));
        top.Controls.Add(new Label { Text = "Workspace", AutoSize = true, Anchor = AnchorStyles.Left }, 0, 0);
        top.Controls.Add(workspace, 1, 0);
        var browseWs = new Button { Text = "Browse…", Dock = DockStyle.Fill }; browseWs.Click += BrowseWorkspace; top.Controls.Add(browseWs, 2, 0);
        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, FlowDirection = FlowDirection.LeftToRight, WrapContents = false };
        var add = new Button { Text = "Add files…", AutoSize = true }; add.Click += AddFiles;
        run.Click += async (_, _) => await RunFilesAsync();
        var clear = new Button { Text = "Clear list", AutoSize = true }; clear.Click += (_, _) => files.Items.Clear();
        var self = new Button { Text = "Runtime self-check", AutoSize = true }; self.Click += async (_, _) => await RunSelfCheckAsync();
        var openWs = new Button { Text = "Open workspace", AutoSize = true }; openWs.Click += (_, _) => OpenPath(workspace.Text);
        var audit = new Button { Text = "Open audit log", AutoSize = true }; audit.Click += (_, _) => OpenPath(Path.Combine(workspace.Text, "audit", "events.jcs.jsonl"));
        buttons.Controls.AddRange(new Control[] { add, run, clear, self, openWs, audit });
        top.SetColumnSpan(buttons, 3); top.Controls.Add(buttons, 0, 1);

        files.Columns.Add("File", 470); files.Columns.Add("Type", 100); files.Columns.Add("Action", 190); files.Columns.Add("Status", 120);
        var split = new SplitContainer { Dock = DockStyle.Fill, Orientation = Orientation.Horizontal, SplitterDistance = 300, Panel1MinSize = 180, Panel2MinSize = 160 };
        split.Panel1.Padding = new Padding(12, 4, 12, 4); split.Panel1.Controls.Add(files);
        split.Panel2.Padding = new Padding(12, 4, 12, 4); split.Panel2.Controls.Add(log);

        var footer = new StatusStrip(); footer.Items.Add(new ToolStripStatusLabel("ENGINEERING PREVIEW — not final release certification")); footer.Items.Add(new ToolStripStatusLabel { Spring = true }); footer.Items.Add(new ToolStripControlHost(state));

        Controls.Add(split); Controls.Add(top); Controls.Add(header); Controls.Add(footer);
        workspace.Text = DefaultWorkspace();
        Append("Engineering Preview loaded. Originals are read-only inputs; captured objects/derivatives are written under the selected workspace.");
    }

    private static string DefaultWorkspace()
    {
        if (Directory.Exists(@"E:\")) return @"E:\MCR_TOOLING_PREVIEW_WORKSPACE";
        return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "MCR Tooling Preview Workspace");
    }

    private void BrowseWorkspace(object? sender, EventArgs e)
    {
        using var d = new FolderBrowserDialog { Description = "Select or create a workspace folder", ShowNewFolderButton = true };
        if (Directory.Exists(workspace.Text)) d.SelectedPath = workspace.Text;
        if (d.ShowDialog(this) == DialogResult.OK) workspace.Text = d.SelectedPath;
    }

    private void AddFiles(object? sender, EventArgs e)
    {
        using var d = new OpenFileDialog { Multiselect = true, Title = "Select evidence files to inspect or ingest", Filter = "Supported/common files|*.pdf;*.zip;*.eml;*.mbox;*.csv;*.docx;*.xlsx;*.pptx|All files|*.*" };
        if (d.ShowDialog(this) != DialogResult.OK) return;
        foreach (var path in d.FileNames)
        {
            if (files.Items.Cast<ListViewItem>().Any(i => string.Equals((string?)i.Tag, path, StringComparison.OrdinalIgnoreCase))) continue;
            var (kind, action) = Classify(path);
            var item = new ListViewItem(new[] { path, kind, action, "Queued" }) { Tag = path };
            files.Items.Add(item);
        }
        state.Text = $"{files.Items.Count} file(s) queued";
    }

    private static (string Kind, string Action) Classify(string path)
    {
        return Path.GetExtension(path).ToLowerInvariant() switch
        {
            ".pdf" => ("PDF", "PDF state inventory"),
            ".zip" => ("ZIP", "Archive inventory"),
            ".eml" => ("EML", "Mail parse/index"),
            ".mbox" => ("MBOX", "Mailbox index"),
            ".csv" => ("CSV", "CSV provenance index"),
            ".docx" or ".xlsx" or ".pptx" => ("OOXML", "OOXML inventory"),
            _ => ("File", "SHA-256 ingest")
        };
    }

    private async Task RunFilesAsync()
    {
        if (files.Items.Count == 0) { MessageBox.Show("Add one or more files first."); return; }
        var ws = workspace.Text.Trim();
        if (string.IsNullOrWhiteSpace(ws)) { MessageBox.Show("Choose a workspace first."); return; }
        try
        {
            run.Enabled = false; state.Text = "Working…"; Directory.CreateDirectory(ws);
            var engine = Program.Full(cfg.engine_path);
            if (!File.Exists(Path.Combine(ws, "mcr-ingest.sqlite3")))
            {
                Append($"> Initialising workspace: {ws}");
                var init = await ProcessRunner.RunAsync(engine, new[] { "init", ws });
                AppendResult(init); if (init.ExitCode != 0) throw new InvalidOperationException("Workspace initialisation failed.");
            }
            var chosen = files.SelectedItems.Count > 0 ? files.SelectedItems.Cast<ListViewItem>().ToArray() : files.Items.Cast<ListViewItem>().ToArray();
            foreach (var item in chosen)
            {
                var path = (string)item.Tag!; item.SubItems[3].Text = "Running"; state.Text = Path.GetFileName(path); Application.DoEvents();
                var args = BuildArgs(ws, path);
                Append($"> {args[0]}  {path}");
                var result = await ProcessRunner.RunAsync(engine, args);
                AppendResult(result);
                item.SubItems[3].Text = result.ExitCode == 0 ? "PASS" : $"FAIL ({result.ExitCode})";
            }
            state.Text = "Finished";
        }
        catch (Exception ex) { Append("ERROR: " + ex); state.Text = "Error"; MessageBox.Show(ex.Message, "MCR Tooling Preview", MessageBoxButtons.OK, MessageBoxIcon.Error); }
        finally { run.Enabled = true; }
    }

    private string[] BuildArgs(string ws, string path)
    {
        return Path.GetExtension(path).ToLowerInvariant() switch
        {
            ".pdf" => new[] { "inventory-pdf", ws, path, Program.Full(cfg.qpdf_path), cfg.qpdf_sha256, Program.Full(cfg.pdfcpu_path), cfg.pdfcpu_sha256 },
            ".zip" => new[] { "inventory-zip", ws, path },
            ".eml" => new[] { "index-eml", ws, path },
            ".mbox" => new[] { "index-mbox", ws, path },
            ".csv" => new[] { "index-csv", ws, path },
            ".docx" or ".xlsx" or ".pptx" => new[] { "inventory-ooxml", ws, path },
            _ => new[] { "ingest-file", ws, path }
        };
    }

    private async Task RunSelfCheckAsync()
    {
        try
        {
            state.Text = "Self-check…"; Append("> Runtime self-check");
            var r = await ProcessRunner.RunAsync(Application.ExecutablePath, new[] { "--self-test" }); AppendResult(r);
            state.Text = r.ExitCode == 0 ? "Self-check PASS" : "Self-check FAIL";
        }
        catch (Exception ex) { Append("ERROR: " + ex); state.Text = "Self-check error"; }
    }

    private void AppendResult(RunResult r)
    {
        if (!string.IsNullOrWhiteSpace(r.StdOut)) Append(r.StdOut.TrimEnd());
        if (!string.IsNullOrWhiteSpace(r.StdErr)) Append(r.StdErr.TrimEnd());
        Append($"[exit {r.ExitCode}]");
    }

    private void Append(string text)
    {
        log.AppendText($"[{DateTime.Now:HH:mm:ss}] {text}{Environment.NewLine}"); log.SelectionStart = log.TextLength; log.ScrollToCaret();
    }

    private void OpenPath(string path)
    {
        try
        {
            if (!File.Exists(path) && !Directory.Exists(path)) { MessageBox.Show("Not created yet:\n" + path); return; }
            Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
        }
        catch (Exception ex) { MessageBox.Show(ex.Message); }
    }
}
