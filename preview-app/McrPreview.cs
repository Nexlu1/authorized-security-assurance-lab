using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace McrPreview
{
    static class App
    {
        public const string EngineSha = "d4589f491c3232f58f34029a3f636d652784574324f881c957f70ad8d0b2f8ba";
        public const string QpdfSha = "59fd63675fbc23787b6d29e0d16eb6f0ea3797920e77e23af86fc674c3425d0d";
        public static string Root { get { return AppDomain.CurrentDomain.BaseDirectory; } }
        public static string Engine { get { return Path.Combine(Root, "bin", "mcr-ingest.exe"); } }

        [STAThread]
        static int Main(string[] args)
        {
            if (args.Any(x => x.Equals("--self-test", StringComparison.OrdinalIgnoreCase)))
                return SelfTest();
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainWindow());
            return 0;
        }

        static int SelfTest()
        {
            try
            {
                RequireHash(Engine, EngineSha, "mcr-ingest.exe");
                string qpdf = FindTool("qpdf.exe");
                RequireHash(qpdf, QpdfSha, "qpdf.exe");
                string pdfcpu = FindTool("pdfcpu.exe");
                Run(Engine, "", 30);
                Run(qpdf, "--version", 30);
                Run(pdfcpu, "version", 30);
                return 0;
            }
            catch { return 2; }
        }

        public static string FindTool(string name)
        {
            string root = Path.Combine(Root, "tools");
            var hits = Directory.Exists(root) ? Directory.GetFiles(root, name, SearchOption.AllDirectories) : new string[0];
            if (hits.Length != 1) throw new Exception("Expected one " + name + ", found " + hits.Length + ".");
            return hits[0];
        }

        public static string Hash(string path)
        {
            using (var sha = SHA256.Create())
            using (var fs = File.OpenRead(path))
                return BitConverter.ToString(sha.ComputeHash(fs)).Replace("-", "").ToLowerInvariant();
        }

        public static void RequireHash(string path, string expected, string label)
        {
            if (!File.Exists(path)) throw new Exception(label + " is missing.");
            string actual = Hash(path);
            if (!actual.Equals(expected, StringComparison.OrdinalIgnoreCase))
                throw new Exception(label + " SHA-256 mismatch.\r\nExpected: " + expected + "\r\nActual:   " + actual);
        }

        // Standard Windows command-line quoting. This preserves ordinary backslashes and
        // correctly doubles only those that precede a literal quote or the closing quote.
        public static string Q(string value)
        {
            if (value == null || value.Length == 0) return "\"\"";
            if (!value.Any(c => char.IsWhiteSpace(c) || c == '"')) return value;
            var b = new StringBuilder();
            b.Append('"');
            int slashes = 0;
            foreach (char c in value)
            {
                if (c == '\\') { slashes++; continue; }
                if (c == '"')
                {
                    b.Append('\\', slashes * 2 + 1);
                    b.Append('"');
                    slashes = 0;
                    continue;
                }
                if (slashes > 0) { b.Append('\\', slashes); slashes = 0; }
                b.Append(c);
            }
            if (slashes > 0) b.Append('\\', slashes * 2);
            b.Append('"');
            return b.ToString();
        }

        public static string Run(string exe, string arguments, int seconds)
        {
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = arguments,
                WorkingDirectory = Root,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true
            };
            using (var p = Process.Start(psi))
            {
                string stdout = p.StandardOutput.ReadToEnd();
                string stderr = p.StandardError.ReadToEnd();
                if (!p.WaitForExit(seconds * 1000))
                {
                    try { p.Kill(); } catch { }
                    throw new Exception(Path.GetFileName(exe) + " timed out.");
                }
                string all = (stdout + (String.IsNullOrWhiteSpace(stderr) ? "" : "\r\n" + stderr)).Trim();
                if (p.ExitCode != 0) throw new Exception(Path.GetFileName(exe) + " exited " + p.ExitCode + ".\r\n" + all);
                return all;
            }
        }
    }

    sealed class MainWindow : Form
    {
        readonly TextBox workspace = new TextBox();
        readonly TextBox source = new TextBox();
        readonly RichTextBox log = new RichTextBox();
        readonly Label status = new Label();
        readonly Label mode = new Label();
        Button[] buttons;

        public MainWindow()
        {
            Text = "MCR Tooling — Engineering Preview";
            StartPosition = FormStartPosition.CenterScreen;
            Width = 1180;
            Height = 780;
            MinimumSize = new Size(920, 620);
            Font = new Font("Segoe UI", 9F);

            var header = new Panel { Dock = DockStyle.Top, Height = 118, Padding = new Padding(24, 16, 24, 8) };
            header.Controls.Add(new Label { Text = "MCR Tooling — Engineering Preview", AutoSize = true, Location = new Point(22, 14), Font = new Font("Segoe UI Semibold", 21F, FontStyle.Bold) });
            header.Controls.Add(new Label { Text = "Runnable R2.4 evidence-ingestion preview · local/offline processing · not final production certification", AutoSize = true, Location = new Point(25, 58) });
            header.Controls.Add(new Label { Text = "Verified engineering milestones: actual Windows target PASS (19/19) · hostile matrix 57/57 functionally exercised", AutoSize = true, Location = new Point(25, 83), Font = new Font("Segoe UI", 9F, FontStyle.Bold) });

            var body = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 5, Padding = new Padding(24, 4, 24, 18) };
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 74));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 74));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 100));
            body.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            body.RowStyles.Add(new RowStyle(SizeType.Absolute, 40));
            body.Controls.Add(PathRow("Workspace", workspace, BrowseWorkspace), 0, 0);
            body.Controls.Add(PathRow("Selected file", source, BrowseSource), 0, 1);
            body.Controls.Add(ActionRow(), 0, 2);

            log.Dock = DockStyle.Fill;
            log.ReadOnly = true;
            log.WordWrap = false;
            log.Font = new Font("Consolas", 9F);
            log.BackColor = SystemColors.Window;
            body.Controls.Add(log, 0, 3);
            body.Controls.Add(Footer(), 0, 4);

            Controls.Add(body);
            Controls.Add(header);

            workspace.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "MCR Tooling Preview Workspace");
            status.Text = "Ready";
            mode.Text = "No file selected";
            Write("Engineering Preview ready.");
            Write("No evidence is uploaded by this app. Processing is local to this PC.");
            Write("Choose a fresh workspace and a file, then use Quick Analyse or a specific operation.");
        }

        Control PathRow(string label, TextBox box, EventHandler browse)
        {
            var p = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 2 };
            p.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            p.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110));
            p.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
            p.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));
            p.Controls.Add(new Label { Text = label, AutoSize = true, Font = new Font("Segoe UI", 9F, FontStyle.Bold), Anchor = AnchorStyles.Left }, 0, 0);
            p.SetColumnSpan(p.GetControlFromPosition(0,0), 2);
            box.Dock = DockStyle.Fill;
            p.Controls.Add(box, 0, 1);
            var b = new Button { Text = "Browse…", Dock = DockStyle.Fill };
            b.Click += browse;
            p.Controls.Add(b, 1, 1);
            return p;
        }

        Control ActionRow()
        {
            var p = new FlowLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(0, 8, 0, 0), AutoScroll = true };
            var quick = B("Quick Analyse");
            var ingest = B("Ingest only");
            var zip = B("ZIP inventory");
            var eml = B("EML index");
            var mbox = B("MBOX index");
            var csv = B("CSV index");
            var office = B("Office / OOXML");
            var pdf = B("PDF inventory");
            var verify = B("Verify package");
            var open = B("Open workspace");
            var clear = B("Clear log");
            buttons = new[] { quick, ingest, zip, eml, mbox, csv, office, pdf, verify, open, clear };
            foreach (var x in buttons) p.Controls.Add(x);
            quick.Click += async (s,e) => await ExecuteAsync(AutoMode());
            ingest.Click += async (s,e) => await ExecuteAsync("ingest-file");
            zip.Click += async (s,e) => await ExecuteAsync("inventory-zip");
            eml.Click += async (s,e) => await ExecuteAsync("index-eml");
            mbox.Click += async (s,e) => await ExecuteAsync("index-mbox");
            csv.Click += async (s,e) => await ExecuteAsync("index-csv");
            office.Click += async (s,e) => await ExecuteAsync("inventory-ooxml");
            pdf.Click += async (s,e) => await ExecuteAsync("inventory-pdf");
            verify.Click += async (s,e) => await VerifyAsync();
            open.Click += (s,e) => OpenWorkspace();
            clear.Click += (s,e) => log.Clear();
            return p;
        }

        Button B(string text) { return new Button { Text = text, Width = 132, Height = 36, Margin = new Padding(0,0,8,8) }; }

        Control Footer()
        {
            var p = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 4 };
            p.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 60));
            p.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            p.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 55));
            p.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            p.Controls.Add(new Label { Text = "Status:", Anchor = AnchorStyles.Left, Font = new Font("Segoe UI", 9F, FontStyle.Bold) },0,0);
            status.Anchor = AnchorStyles.Left; p.Controls.Add(status,1,0);
            p.Controls.Add(new Label { Text = "Mode:", Anchor = AnchorStyles.Left, Font = new Font("Segoe UI", 9F, FontStyle.Bold) },2,0);
            mode.Anchor = AnchorStyles.Left; p.Controls.Add(mode,3,0);
            return p;
        }

        void BrowseWorkspace(object s, EventArgs e)
        {
            using (var d = new FolderBrowserDialog { Description = "Choose the local MCR Tooling preview workspace" })
            {
                if (Directory.Exists(workspace.Text)) d.SelectedPath = workspace.Text;
                if (d.ShowDialog(this) == DialogResult.OK) workspace.Text = d.SelectedPath;
            }
        }

        void BrowseSource(object s, EventArgs e)
        {
            using (var d = new OpenFileDialog { Title = "Choose a file to analyse", Filter = "All files (*.*)|*.*" })
                if (d.ShowDialog(this) == DialogResult.OK) { source.Text = d.FileName; mode.Text = ModeFor(Path.GetExtension(d.FileName)); }
        }

        string AutoMode()
        {
            if (!File.Exists(source.Text)) { MessageBox.Show(this,"Choose an existing file first."); return null; }
            return ModeFor(Path.GetExtension(source.Text));
        }

        static string ModeFor(string ext)
        {
            switch ((ext ?? "").ToLowerInvariant())
            {
                case ".zip": return "inventory-zip";
                case ".eml": return "index-eml";
                case ".mbox": return "index-mbox";
                case ".csv": return "index-csv";
                case ".docx": case ".xlsx": case ".pptx": return "inventory-ooxml";
                case ".pdf": return "inventory-pdf";
                default: return "ingest-file";
            }
        }

        async Task ExecuteAsync(string command)
        {
            if (String.IsNullOrWhiteSpace(command)) return;
            if (!File.Exists(source.Text)) { MessageBox.Show(this,"Choose an existing file first."); return; }
            string ws = workspace.Text.Trim();
            if (ws.Length == 0) { MessageBox.Show(this,"Choose a workspace first."); return; }
            Directory.CreateDirectory(ws);
            await Busy(async () =>
            {
                mode.Text = command;
                Write("------------------------------------------------------------");
                Write(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + command);
                Write("Source: " + source.Text);
                Write("Workspace: " + ws);
                await Task.Run(() => EnsureWorkspace(ws));
                string args;
                if (command == "inventory-pdf")
                {
                    string qpdf = App.FindTool("qpdf.exe");
                    string pdfcpu = App.FindTool("pdfcpu.exe");
                    args = "inventory-pdf " + App.Q(ws) + " " + App.Q(source.Text) + " " + App.Q(qpdf) + " " + App.Hash(qpdf) + " " + App.Q(pdfcpu) + " " + App.Hash(pdfcpu);
                }
                else args = command + " " + App.Q(ws) + " " + App.Q(source.Text);
                string output = await Task.Run(() => App.Run(App.Engine, args, 600));
                Write(output);
                Write("Completed successfully.");
                status.Text = "PASS";
            });
        }

        void EnsureWorkspace(string ws)
        {
            if (!File.Exists(Path.Combine(ws,"mcr-ingest.sqlite3")))
                App.Run(App.Engine, "init " + App.Q(ws), 120);
        }

        async Task VerifyAsync()
        {
            await Busy(async () =>
            {
                Write("------------------------------------------------------------");
                Write("Verifying bundled executables…");
                await Task.Run(() => App.RequireHash(App.Engine, App.EngineSha, "mcr-ingest.exe"));
                string qpdf = App.FindTool("qpdf.exe");
                await Task.Run(() => App.RequireHash(qpdf, App.QpdfSha, "qpdf.exe"));
                string pdfcpu = App.FindTool("pdfcpu.exe");
                Write("mcr-ingest.exe: " + App.Hash(App.Engine) + "  PASS");
                Write("qpdf.exe:       " + App.Hash(qpdf) + "  PASS");
                Write("pdfcpu.exe:     " + App.Hash(pdfcpu) + "  recorded");
                status.Text = "PASS";
            });
        }

        async Task Busy(Func<Task> work)
        {
            foreach (var b in buttons) b.Enabled = false;
            Cursor = Cursors.WaitCursor;
            status.Text = "Working…";
            try { await work(); }
            catch (Exception ex) { status.Text = "FAIL"; Write("ERROR: " + ex.Message); MessageBox.Show(this, ex.Message, "MCR Tooling Preview", MessageBoxButtons.OK, MessageBoxIcon.Error); }
            finally { foreach (var b in buttons) b.Enabled = true; Cursor = Cursors.Default; }
        }

        void OpenWorkspace()
        {
            string ws = workspace.Text.Trim();
            if (ws.Length == 0) return;
            Directory.CreateDirectory(ws);
            Process.Start(new ProcessStartInfo { FileName = "explorer.exe", Arguments = App.Q(ws), UseShellExecute = true });
        }

        void Write(string text)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(Write), text); return; }
            log.AppendText((text ?? "") + Environment.NewLine);
            log.SelectionStart = log.TextLength;
            log.ScrollToCaret();
        }
    }
}
