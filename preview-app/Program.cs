using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace McrToolingPreview
{
    internal static class Program
    {
        internal const string ExpectedEngineSha256 = "d4589f491c3232f58f34029a3f636d652784574324f881c957f70ad8d0b2f8ba";
        internal const string ExpectedQpdfSha256 = "59fd63675fbc23787b6d29e0d16eb6f0ea3797920e77e23af86fc674c3425d0d";

        [STAThread]
        private static int Main(string[] args)
        {
            if (args.Any(a => string.Equals(a, "--self-test", StringComparison.OrdinalIgnoreCase)))
                return SelfTest();

            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new PreviewForm());
            return 0;
        }

        private static int SelfTest()
        {
            try
            {
                string root = AppDomain.CurrentDomain.BaseDirectory;
                string engine = Path.Combine(root, "bin", "mcr-ingest.exe");
                if (!File.Exists(engine)) throw new Exception("mcr-ingest.exe missing");
                string engineSha = HashFile(engine);
                if (!engineSha.Equals(ExpectedEngineSha256, StringComparison.OrdinalIgnoreCase))
                    throw new Exception("mcr-ingest.exe SHA-256 mismatch: " + engineSha);

                string qpdf = FindSingle(root, "tools", "qpdf.exe");
                string qpdfSha = HashFile(qpdf);
                if (!qpdfSha.Equals(ExpectedQpdfSha256, StringComparison.OrdinalIgnoreCase))
                    throw new Exception("qpdf.exe SHA-256 mismatch: " + qpdfSha);

                string pdfcpu = FindSingle(root, "tools", "pdfcpu.exe");
                RunProcess(engine, "", 30);
                RunProcess(qpdf, "--version", 30);
                RunProcess(pdfcpu, "version", 30);

                Console.WriteLine("PASS MCR Tooling Engineering Preview self-test");
                Console.WriteLine("engine_sha256=" + engineSha);
                Console.WriteLine("qpdf_sha256=" + qpdfSha);
                Console.WriteLine("pdfcpu_sha256=" + HashFile(pdfcpu));
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("FAIL: " + ex.Message);
                return 2;
            }
        }

        internal static string HashFile(string path)
        {
            using (var sha = SHA256.Create())
            using (var fs = File.OpenRead(path))
            {
                return BitConverter.ToString(sha.ComputeHash(fs)).Replace("-", "").ToLowerInvariant();
            }
        }

        internal static string FindSingle(string root, string under, string fileName)
        {
            string dir = Path.Combine(root, under);
            if (!Directory.Exists(dir)) throw new Exception("tool directory missing: " + dir);
            var matches = Directory.GetFiles(dir, fileName, SearchOption.AllDirectories);
            if (matches.Length != 1) throw new Exception("expected one " + fileName + ", found " + matches.Length);
            return matches[0];
        }

        internal static string RunProcess(string exe, string arguments, int timeoutSeconds)
        {
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = arguments,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory
            };
            using (var p = Process.Start(psi))
            {
                string stdout = p.StandardOutput.ReadToEnd();
                string stderr = p.StandardError.ReadToEnd();
                if (!p.WaitForExit(timeoutSeconds * 1000))
                {
                    try { p.Kill(); } catch { }
                    throw new Exception(Path.GetFileName(exe) + " timed out");
                }
                if (p.ExitCode != 0)
                    throw new Exception(Path.GetFileName(exe) + " exited " + p.ExitCode + "\r\n" + stdout + "\r\n" + stderr);
                return (stdout + (string.IsNullOrWhiteSpace(stderr) ? "" : "\r\n" + stderr)).Trim();
            }
        }

        internal static string Quote(string value)
        {
            if (value == null) return "\"\"";
            return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
        }
    }

    internal sealed class PreviewForm : Form
    {
        private readonly TextBox workspaceBox = new TextBox();
        private readonly TextBox fileBox = new TextBox();
        private readonly RichTextBox logBox = new RichTextBox();
        private readonly Label statusValue = new Label();
        private readonly Label modeValue = new Label();
        private readonly Button quickButton = new Button();
        private readonly Button ingestButton = new Button();
        private readonly Button zipButton = new Button();
        private readonly Button emlButton = new Button();
        private readonly Button mboxButton = new Button();
        private readonly Button csvButton = new Button();
        private readonly Button officeButton = new Button();
        private readonly Button pdfButton = new Button();
        private readonly Button verifyButton = new Button();
        private readonly Button openWorkspaceButton = new Button();
        private readonly Button clearButton = new Button();
        private Button[] actionButtons;

        private string Root => AppDomain.CurrentDomain.BaseDirectory;
        private string Engine => Path.Combine(Root, "bin", "mcr-ingest.exe");

        public PreviewForm()
        {
            Text = "MCR Tooling — Engineering Preview";
            Width = 1120;
            Height = 760;
            MinimumSize = new Size(900, 620);
            StartPosition = FormStartPosition.CenterScreen;
            Font = new Font("Segoe UI", 9F);

            var top = new Panel { Dock = DockStyle.Top, Height = 112, Padding = new Padding(22, 16, 22, 10) };
            var title = new Label
            {
                AutoSize = true,
                Font = new Font("Segoe UI Semibold", 20F, FontStyle.Bold),
                Text = "MCR Tooling — Engineering Preview",
                Location = new Point(20, 12)
            };
            var subtitle = new Label
            {
                AutoSize = true,
                Text = "Working R2.4 evidence-ingestion engine · offline/local · current preview, not final production certification",
                Location = new Point(23, 53)
            };
            var milestone = new Label
            {
                AutoSize = true,
                Font = new Font("Segoe UI", 9F, FontStyle.Bold),
                Text = "Engineering evidence: real Windows target PASS (19/19) · hostile matrix 57/57 functionally exercised",
                Location = new Point(23, 77)
            };
            top.Controls.Add(title);
            top.Controls.Add(subtitle);
            top.Controls.Add(milestone);

            var main = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 5,
                Padding = new Padding(22, 8, 22, 16)
            };
            main.RowStyles.Add(new RowStyle(SizeType.Absolute, 80));
            main.RowStyles.Add(new RowStyle(SizeType.Absolute, 80));
            main.RowStyles.Add(new RowStyle(SizeType.Absolute, 110));
            main.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            main.RowStyles.Add(new RowStyle(SizeType.Absolute, 42));

            main.Controls.Add(BuildPathRow("Workspace", workspaceBox, BrowseWorkspace), 0, 0);
            main.Controls.Add(BuildPathRow("Selected file", fileBox, BrowseFile), 0, 1);
            main.Controls.Add(BuildActionPanel(), 0, 2);

            logBox.Dock = DockStyle.Fill;
            logBox.ReadOnly = true;
            logBox.Font = new Font("Consolas", 9F);
            logBox.WordWrap = false;
            logBox.BackColor = SystemColors.Window;
            main.Controls.Add(logBox, 0, 3);
            main.Controls.Add(BuildFooter(), 0, 4);

            Controls.Add(main);
            Controls.Add(top);

            workspaceBox.Text = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "MCR Tooling Preview Workspace");
            statusValue.Text = "Ready";
            modeValue.Text = "No file selected";
            AppendLog("Engineering Preview ready.");
            AppendLog("This build runs locally. It does not upload evidence or make network calls.");
            AppendLog("Source files are read as input; the engine writes controlled derivatives/state to the selected workspace.");
        }

        private Control BuildPathRow(string labelText, TextBox box, EventHandler browseHandler)
        {
            var panel = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, RowCount = 2 };
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 120));
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 110));
            panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 24));
            panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 34));

            var label = new Label { Text = labelText, AutoSize = true, Font = new Font("Segoe UI", 9F, FontStyle.Bold), Anchor = AnchorStyles.Left };
            box.Dock = DockStyle.Fill;
            var browse = new Button { Text = "Browse…", Dock = DockStyle.Fill };
            browse.Click += browseHandler;

            panel.Controls.Add(label, 0, 0);
            panel.SetColumnSpan(label, 3);
            panel.Controls.Add(new Label { Text = "", Dock = DockStyle.Fill }, 0, 1);
            panel.Controls.Add(box, 1, 1);
            panel.Controls.Add(browse, 2, 1);
            return panel;
        }

        private Control BuildActionPanel()
        {
            var panel = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoScroll = true, Padding = new Padding(0, 8, 0, 4) };
            quickButton.Text = "Quick Analyse";
            ingestButton.Text = "Ingest only";
            zipButton.Text = "ZIP inventory";
            emlButton.Text = "EML index";
            mboxButton.Text = "MBOX index";
            csvButton.Text = "CSV index";
            officeButton.Text = "Office / OOXML";
            pdfButton.Text = "PDF inventory";
            verifyButton.Text = "Verify package";
            openWorkspaceButton.Text = "Open workspace";
            clearButton.Text = "Clear log";

            actionButtons = new[] { quickButton, ingestButton, zipButton, emlButton, mboxButton, csvButton, officeButton, pdfButton, verifyButton, openWorkspaceButton, clearButton };
            foreach (var b in actionButtons)
            {
                b.Width = 128;
                b.Height = 36;
                b.Margin = new Padding(0, 0, 8, 8);
                panel.Controls.Add(b);
            }

            quickButton.Click += async (s, e) => await RunQuickAsync();
            ingestButton.Click += async (s, e) => await RunModeAsync("ingest-file");
            zipButton.Click += async (s, e) => await RunModeAsync("inventory-zip");
            emlButton.Click += async (s, e) => await RunModeAsync("index-eml");
            mboxButton.Click += async (s, e) => await RunModeAsync("index-mbox");
            csvButton.Click += async (s, e) => await RunModeAsync("index-csv");
            officeButton.Click += async (s, e) => await RunModeAsync("inventory-ooxml");
            pdfButton.Click += async (s, e) => await RunModeAsync("inventory-pdf");
            verifyButton.Click += async (s, e) => await VerifyPackageAsync();
            openWorkspaceButton.Click += (s, e) => OpenWorkspace();
            clearButton.Click += (s, e) => logBox.Clear();
            return panel;
        }

        private Control BuildFooter()
        {
            var panel = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 4, RowCount = 1 };
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 70));
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 70));
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50));
            panel.Controls.Add(new Label { Text = "Status:", Anchor = AnchorStyles.Left, Font = new Font("Segoe UI", 9F, FontStyle.Bold) }, 0, 0);
            statusValue.Anchor = AnchorStyles.Left;
            panel.Controls.Add(statusValue, 1, 0);
            panel.Controls.Add(new Label { Text = "Mode:", Anchor = AnchorStyles.Left, Font = new Font("Segoe UI", 9F, FontStyle.Bold) }, 2, 0);
            modeValue.Anchor = AnchorStyles.Left;
            panel.Controls.Add(modeValue, 3, 0);
            return panel;
        }

        private void BrowseWorkspace(object sender, EventArgs e)
        {
            using (var dlg = new FolderBrowserDialog { Description = "Choose the MCR Tooling preview workspace" })
            {
                if (Directory.Exists(workspaceBox.Text)) dlg.SelectedPath = workspaceBox.Text;
                if (dlg.ShowDialog(this) == DialogResult.OK) workspaceBox.Text = dlg.SelectedPath;
            }
        }

        private void BrowseFile(object sender, EventArgs e)
        {
            using (var dlg = new OpenFileDialog { Title = "Choose a file to analyse", Filter = "All files (*.*)|*.*" })
            {
                if (dlg.ShowDialog(this) == DialogResult.OK)
                {
                    fileBox.Text = dlg.FileName;
                    modeValue.Text = ModeForExtension(Path.GetExtension(dlg.FileName));
                }
            }
        }

        private async Task RunQuickAsync()
        {
            string file = RequireFile();
            if (file == null) return;
            await RunModeAsync(ModeForExtension(Path.GetExtension(file)));
        }

        private static string ModeForExtension(string ext)
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

        private string RequireFile()
        {
            string file = (fileBox.Text ?? "").Trim();
            if (!File.Exists(file))
            {
                MessageBox.Show(this, "Choose an existing file first.", "MCR Tooling Preview", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return null;
            }
            return file;
        }

        private string RequireWorkspace()
        {
            string workspace = (workspaceBox.Text ?? "").Trim();
            if (string.IsNullOrWhiteSpace(workspace))
            {
                MessageBox.Show(this, "Choose a workspace folder first.", "MCR Tooling Preview", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return null;
            }
            Directory.CreateDirectory(workspace);
            return workspace;
        }

        private async Task RunModeAsync(string mode)
        {
            string file = RequireFile();
            string workspace = RequireWorkspace();
            if (file == null || workspace == null) return;

            await BusyAsync(async () =>
            {
                modeValue.Text = mode;
                AppendLog("------------------------------------------------------------");
                AppendLog(DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + mode);
                AppendLog("Source: " + file);
                AppendLog("Workspace: " + workspace);

                await Task.Run(() => EnsureWorkspace(workspace));

                string args;
                if (mode == "inventory-pdf")
                {
                    string qpdf = Program.FindSingle(Root, "tools", "qpdf.exe");
                    string pdfcpu = Program.FindSingle(Root, "tools", "pdfcpu.exe");
                    string qpdfSha = Program.HashFile(qpdf);
                    string pdfcpuSha = Program.HashFile(pdfcpu);
                    args = "inventory-pdf " + Program.Quote(workspace) + " " + Program.Quote(file) + " " + Program.Quote(qpdf) + " " + qpdfSha + " " + Program.Quote(pdfcpu) + " " + pdfcpuSha;
                }
                else
                {
                    args = mode + " " + Program.Quote(workspace) + " " + Program.Quote(file);
                }

                string output = await Task.Run(() => Program.RunProcess(Engine, args, 600));
                AppendLog(output);
                AppendLog("Completed successfully.");
                statusValue.Text = "PASS";
            });
        }

        private void EnsureWorkspace(string workspace)
        {
            string db = Path.Combine(workspace, "mcr-ingest.sqlite3");
            if (!File.Exists(db))
                Program.RunProcess(Engine, "init " + Program.Quote(workspace), 120);
        }

        private async Task VerifyPackageAsync()
        {
            await BusyAsync(async () =>
            {
                AppendLog("------------------------------------------------------------");
                AppendLog("Verifying bundled engine and specialist tools…");
                string engineSha = await Task.Run(() => Program.HashFile(Engine));
                string qpdf = Program.FindSingle(Root, "tools", "qpdf.exe");
                string qpdfSha = await Task.Run(() => Program.HashFile(qpdf));
                string pdfcpu = Program.FindSingle(Root, "tools", "pdfcpu.exe");
                string pdfcpuSha = await Task.Run(() => Program.HashFile(pdfcpu));

                if (!engineSha.Equals(Program.ExpectedEngineSha256, StringComparison.OrdinalIgnoreCase))
                    throw new Exception("mcr-ingest.exe hash mismatch: " + engineSha);
                if (!qpdfSha.Equals(Program.ExpectedQpdfSha256, StringComparison.OrdinalIgnoreCase))
                    throw new Exception("qpdf.exe hash mismatch: " + qpdfSha);

                AppendLog("mcr-ingest.exe SHA-256: " + engineSha + "  PASS");
                AppendLog("qpdf.exe SHA-256:       " + qpdfSha + "  PASS");
                AppendLog("pdfcpu.exe SHA-256:     " + pdfcpuSha + "  recorded");
                AppendLog("Package verification complete.");
                statusValue.Text = "PASS";
            });
        }

        private async Task BusyAsync(Func<Task> work)
        {
            SetBusy(true);
            statusValue.Text = "Working…";
            try
            {
                await work();
            }
            catch (Exception ex)
            {
                statusValue.Text = "FAIL";
                AppendLog("ERROR: " + ex.Message);
                MessageBox.Show(this, ex.Message, "MCR Tooling Preview", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                SetBusy(false);
            }
        }

        private void SetBusy(bool busy)
        {
            foreach (var b in actionButtons) b.Enabled = !busy;
            Cursor = busy ? Cursors.WaitCursor : Cursors.Default;
        }

        private void OpenWorkspace()
        {
            string workspace = RequireWorkspace();
            if (workspace == null) return;
            Process.Start(new ProcessStartInfo { FileName = "explorer.exe", Arguments = Program.Quote(workspace), UseShellExecute = true });
        }

        private void AppendLog(string text)
        {
            if (InvokeRequired)
            {
                BeginInvoke(new Action<string>(AppendLog), text);
                return;
            }
            logBox.AppendText((text ?? "") + Environment.NewLine);
            logBox.SelectionStart = logBox.TextLength;
            logBox.ScrollToCaret();
        }
    }
}
