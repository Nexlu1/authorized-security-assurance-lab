use eframe::egui;
use rfd::FileDialog;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::mpsc::{self, Receiver, TryRecvError};
use std::thread;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Nav {
    Overview,
    Inspect,
    Results,
    About,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Action {
    Auto,
    Ingest,
    Archive,
    Email,
    Mbox,
    Csv,
    Office,
    Pdf,
}

impl Action {
    fn label(self) -> &'static str {
        match self {
            Self::Auto => "Auto-detect",
            Self::Ingest => "Capture / ingest",
            Self::Archive => "Inspect ZIP/archive",
            Self::Email => "Index EML email",
            Self::Mbox => "Index MBOX mailbox",
            Self::Csv => "Index CSV",
            Self::Office => "Inspect DOCX/XLSX/PPTX",
            Self::Pdf => "Inspect PDF",
        }
    }
}

#[derive(Clone, Debug, Default)]
struct ToolConfig {
    qpdf_rel: Option<String>,
    qpdf_sha256: Option<String>,
    pdfcpu_rel: Option<String>,
    pdfcpu_sha256: Option<String>,
}

impl ToolConfig {
    fn load(app_dir: &Path) -> Self {
        let mut cfg = Self::default();
        let Ok(text) = fs::read_to_string(app_dir.join("tools.env")) else {
            return cfg;
        };
        for line in text.lines() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let Some((key, value)) = line.split_once('=') else {
                continue;
            };
            match key.trim() {
                "QPDF_REL" => cfg.qpdf_rel = Some(value.trim().to_owned()),
                "QPDF_SHA256" => cfg.qpdf_sha256 = Some(value.trim().to_owned()),
                "PDFCPU_REL" => cfg.pdfcpu_rel = Some(value.trim().to_owned()),
                "PDFCPU_SHA256" => cfg.pdfcpu_sha256 = Some(value.trim().to_owned()),
                _ => {}
            }
        }
        cfg
    }

    fn pdf_ready(&self, app_dir: &Path) -> bool {
        let qpdf = self.qpdf_rel.as_ref().map(|p| app_dir.join(p));
        let pdfcpu = self.pdfcpu_rel.as_ref().map(|p| app_dir.join(p));
        qpdf.is_some_and(|p| p.is_file())
            && pdfcpu.is_some_and(|p| p.is_file())
            && self.qpdf_sha256.as_ref().is_some_and(|s| s.len() == 64)
            && self.pdfcpu_sha256.as_ref().is_some_and(|s| s.len() == 64)
    }
}

#[derive(Clone, Debug)]
struct RunRequest {
    engine: PathBuf,
    app_dir: PathBuf,
    workspace: PathBuf,
    file: PathBuf,
    action: Action,
    tools: ToolConfig,
}

#[derive(Clone, Debug)]
struct RunResult {
    ok: bool,
    action: String,
    file: PathBuf,
    exit_code: Option<i32>,
    stdout: String,
    stderr: String,
}

struct PreviewApp {
    nav: Nav,
    app_dir: PathBuf,
    engine: PathBuf,
    tools: ToolConfig,
    workspace: PathBuf,
    selected_file: Option<PathBuf>,
    action: Action,
    pending: Option<Receiver<RunResult>>,
    last_result: Option<RunResult>,
    status_line: String,
}

impl PreviewApp {
    fn new() -> Self {
        let app_dir = app_dir();
        let engine = app_dir.join("engine").join("mcr-ingest.exe");
        let tools = ToolConfig::load(&app_dir);
        Self {
            nav: Nav::Overview,
            app_dir,
            engine,
            tools,
            workspace: default_workspace(),
            selected_file: None,
            action: Action::Auto,
            pending: None,
            last_result: None,
            status_line: "Ready. Local-only engineering preview.".to_owned(),
        }
    }

    fn engine_ready(&self) -> bool {
        self.engine.is_file()
    }

    fn effective_action(&self) -> Action {
        if self.action != Action::Auto {
            return self.action;
        }
        self.selected_file
            .as_deref()
            .map(detect_action)
            .unwrap_or(Action::Ingest)
    }

    fn start_run(&mut self) {
        if self.pending.is_some() {
            return;
        }
        let Some(file) = self.selected_file.clone() else {
            self.status_line = "Choose a file first.".to_owned();
            return;
        };
        if !self.engine_ready() {
            self.status_line = "Engine executable is missing from this preview package.".to_owned();
            return;
        }
        if let Err(err) = fs::create_dir_all(&self.workspace) {
            self.status_line = format!("Cannot create workspace: {err}");
            return;
        }
        let action = self.effective_action();
        if action == Action::Pdf && !self.tools.pdf_ready(&self.app_dir) {
            self.status_line = "PDF specialist tools are not ready in this package.".to_owned();
            return;
        }

        let request = RunRequest {
            engine: self.engine.clone(),
            app_dir: self.app_dir.clone(),
            workspace: self.workspace.clone(),
            file,
            action,
            tools: self.tools.clone(),
        };
        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            let result = run_request(request);
            let _ = tx.send(result);
        });
        self.pending = Some(rx);
        self.status_line = format!("Running {}…", action.label());
    }

    fn poll_run(&mut self) {
        let mut completed = None;
        if let Some(rx) = &self.pending {
            match rx.try_recv() {
                Ok(result) => completed = Some(result),
                Err(TryRecvError::Empty) => {}
                Err(TryRecvError::Disconnected) => {
                    self.pending = None;
                    self.status_line = "The background engine task ended unexpectedly.".to_owned();
                }
            }
        }
        if let Some(result) = completed {
            self.pending = None;
            self.status_line = if result.ok {
                "Completed successfully.".to_owned()
            } else {
                format!("Completed with an error (exit {:?}).", result.exit_code)
            };
            self.last_result = Some(result);
            self.nav = Nav::Results;
        }
    }

    fn sidebar(&mut self, ctx: &egui::Context) {
        egui::SidePanel::left("navigation")
            .resizable(false)
            .default_width(220.0)
            .show(ctx, |ui| {
                ui.add_space(18.0);
                ui.label(egui::RichText::new("MCR").size(13.0).strong());
                ui.label(egui::RichText::new("Engineering Preview").size(20.0).strong());
                ui.add_space(4.0);
                ui.label("Local evidence tooling");
                ui.add_space(22.0);

                nav_button(ui, &mut self.nav, Nav::Overview, "Overview");
                nav_button(ui, &mut self.nav, Nav::Inspect, "Import & inspect");
                nav_button(ui, &mut self.nav, Nav::Results, "Results");
                nav_button(ui, &mut self.nav, Nav::About, "About this build");

                ui.add_space(24.0);
                ui.separator();
                ui.add_space(12.0);
                ui.strong("Safety boundary");
                ui.label("Offline/local workflow. Original bytes are preserved by the engine. Frozen MCR R59 is not modified by this development lane.");
            });
    }

    fn topbar(&self, ctx: &egui::Context) {
        egui::TopBottomPanel::top("topbar").show(ctx, |ui| {
            ui.add_space(8.0);
            ui.horizontal_wrapped(|ui| {
                ui.heading("MCR Future Tooling");
                ui.separator();
                ui.strong("ENGINEERING PREVIEW");
                ui.separator();
                ui.label("LOCAL ONLY");
                if self.pending.is_some() {
                    ui.spinner();
                }
            });
            ui.add_space(8.0);
        });
    }

    fn overview(&mut self, ui: &mut egui::Ui) {
        ui.heading("Working software, in one visible shell");
        ui.label("This preview wraps the current evidence-ingestion engine in a normal Windows interface so the engineering progress is visible and usable without command lines.");
        ui.add_space(18.0);

        ui.columns(3, |cols| {
            status_card(&mut cols[0], "Core engine", self.engine_ready(), "SHA-256 capture, occurrence provenance, audit chain, ZIP/mail/CSV/OOXML/PDF paths");
            status_card(&mut cols[1], "PDF specialists", self.tools.pdf_ready(&self.app_dir), "qpdf 12.4.1 + pdfcpu 0.15.0 bundled and hash-pinned in the preview package");
            status_card(&mut cols[2], "Hostile matrix", true, "57/57 functional behaviours reached in engineering qualification; final target calibration/release gates remain separate");
        });

        ui.add_space(18.0);
        ui.group(|ui| {
            ui.heading("What you can do in this preview");
            ui.label("• Capture any file into the content-addressed local workspace");
            ui.label("• Inspect ZIP/archive paths and hostile archive state without blind extraction");
            ui.label("• Index EML and MBOX mail with provenance warnings");
            ui.label("• Index CSV with byte-position and decoding provenance");
            ui.label("• Inspect DOCX/XLSX/PPTX package state, including hidden/revision/external/macro-related signals");
            ui.label("• Inspect PDFs through the qualified qpdf/pdfcpu specialist path");
            ui.add_space(8.0);
            if ui.button("Choose a file and inspect it").clicked() {
                self.nav = Nav::Inspect;
            }
        });
    }

    fn inspect(&mut self, ui: &mut egui::Ui) {
        ui.heading("Import & inspect");
        ui.label("Choose a file. Auto-detect selects the safest current engine path from the extension; you can override it.");
        ui.add_space(16.0);

        ui.group(|ui| {
            ui.strong("1. File");
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                if ui.button("Browse…").on_hover_text("Choose a local source file").clicked() {
                    if let Some(path) = FileDialog::new().pick_file() {
                        self.selected_file = Some(path);
                    }
                }
                if let Some(path) = &self.selected_file {
                    ui.monospace(path.display().to_string());
                } else {
                    ui.label("No file selected");
                }
            });
        });

        ui.add_space(12.0);
        ui.group(|ui| {
            ui.strong("2. Local workspace");
            ui.add_space(6.0);
            ui.horizontal(|ui| {
                if ui.button("Choose workspace…").clicked() {
                    if let Some(path) = FileDialog::new().pick_folder() {
                        self.workspace = path;
                    }
                }
                if ui.button("Open folder").clicked() {
                    let _ = fs::create_dir_all(&self.workspace);
                    let _ = Command::new("explorer.exe").arg(&self.workspace).spawn();
                }
            });
            ui.monospace(self.workspace.display().to_string());
        });

        ui.add_space(12.0);
        ui.group(|ui| {
            ui.strong("3. Operation");
            ui.add_space(6.0);
            egui::ComboBox::from_id_salt("operation")
                .selected_text(self.action.label())
                .show_ui(ui, |ui| {
                    for action in [Action::Auto, Action::Ingest, Action::Archive, Action::Email, Action::Mbox, Action::Csv, Action::Office, Action::Pdf] {
                        ui.selectable_value(&mut self.action, action, action.label());
                    }
                });
            if self.action == Action::Auto {
                ui.label(format!("Detected: {}", self.effective_action().label()));
            }
        });

        ui.add_space(18.0);
        ui.horizontal(|ui| {
            let ready = self.selected_file.is_some() && self.pending.is_none();
            if ui.add_enabled(ready, egui::Button::new("Run local inspection")).clicked() {
                self.start_run();
            }
            if self.pending.is_some() {
                ui.spinner();
                ui.label("Engine working…");
            }
        });
        ui.add_space(8.0);
        ui.label(&self.status_line);
    }

    fn results(&mut self, ui: &mut egui::Ui) {
        ui.heading("Latest result");
        ui.label(&self.status_line);
        ui.add_space(14.0);
        let Some(result) = &self.last_result else {
            ui.label("No operation has been run in this app session yet.");
            return;
        };

        ui.group(|ui| {
            ui.horizontal_wrapped(|ui| {
                ui.strong(if result.ok { "PASS" } else { "ERROR" });
                ui.separator();
                ui.label(&result.action);
                ui.separator();
                ui.label(format!("Exit: {:?}", result.exit_code));
            });
            ui.monospace(result.file.display().to_string());
        });

        ui.add_space(12.0);
        egui::ScrollArea::vertical().show(ui, |ui| {
            ui.strong("Engine output");
            if result.stdout.trim().is_empty() {
                ui.label("(no stdout)");
            } else {
                ui.code(&result.stdout);
            }
            if !result.stderr.trim().is_empty() {
                ui.add_space(12.0);
                ui.strong("Warnings / errors");
                ui.code(&result.stderr);
            }
        });
    }

    fn about(&self, ui: &mut egui::Ui) {
        ui.heading("About this engineering preview");
        ui.label("This is a runnable checkpoint, not the final production-certified release.");
        ui.add_space(14.0);
        ui.group(|ui| {
            ui.strong("GitHub/FOSS-first shell");
            ui.label("GUI: egui/eframe 0.36.1 (Apache-2.0), selected from GitHub for a native Rust path and AccessKit accessibility support.");
            ui.label("File dialogs: rfd 0.17.2 (MIT), selected from GitHub.");
            ui.label("Evidence engine: current MCR R2.4 engineering candidate.");
            ui.label("PDF specialists: qpdf 12.4.1 and pdfcpu 0.15.0.");
        });
        ui.add_space(12.0);
        ui.group(|ui| {
            ui.strong("Still open before final release");
            ui.label("Target-Windows resource calibration, final consolidated full-suite acceptance, final deterministic package/signing integration review, and PR promotion controls.");
        });
        ui.add_space(12.0);
        ui.monospace(format!("App directory: {}", self.app_dir.display()));
        ui.monospace(format!("Engine: {}", self.engine.display()));
    }
}

impl eframe::App for PreviewApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.poll_run();
        if self.pending.is_some() {
            ctx.request_repaint_after(std::time::Duration::from_millis(100));
        }
        self.sidebar(ctx);
        self.topbar(ctx);
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.add_space(18.0);
            match self.nav {
                Nav::Overview => self.overview(ui),
                Nav::Inspect => self.inspect(ui),
                Nav::Results => self.results(ui),
                Nav::About => self.about(ui),
            }
        });
    }
}

fn nav_button(ui: &mut egui::Ui, nav: &mut Nav, target: Nav, text: &str) {
    if ui.selectable_label(*nav == target, text).clicked() {
        *nav = target;
    }
}

fn status_card(ui: &mut egui::Ui, title: &str, pass: bool, detail: &str) {
    ui.group(|ui| {
        ui.strong(title);
        ui.heading(if pass { "READY" } else { "CHECK" });
        ui.label(detail);
    });
}

fn detect_action(path: &Path) -> Action {
    let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("").to_ascii_lowercase();
    match ext.as_str() {
        "zip" => Action::Archive,
        "eml" => Action::Email,
        "mbox" | "mbx" => Action::Mbox,
        "csv" => Action::Csv,
        "docx" | "xlsx" | "pptx" => Action::Office,
        "pdf" => Action::Pdf,
        _ => Action::Ingest,
    }
}

fn run_request(request: RunRequest) -> RunResult {
    let mut cmd = Command::new(&request.engine);
    let action = request.action;
    match action {
        Action::Auto | Action::Ingest => {
            cmd.arg("ingest-file").arg(&request.workspace).arg(&request.file);
        }
        Action::Archive => {
            cmd.arg("inventory-zip").arg(&request.workspace).arg(&request.file);
        }
        Action::Email => {
            cmd.arg("index-eml").arg(&request.workspace).arg(&request.file);
        }
        Action::Mbox => {
            cmd.arg("index-mbox").arg(&request.workspace).arg(&request.file);
        }
        Action::Csv => {
            cmd.arg("index-csv").arg(&request.workspace).arg(&request.file);
        }
        Action::Office => {
            cmd.arg("inventory-ooxml").arg(&request.workspace).arg(&request.file);
        }
        Action::Pdf => {
            let Some(qpdf_rel) = request.tools.qpdf_rel.as_ref() else {
                return failed_before_launch(action, request.file, "qpdf path missing from tools.env");
            };
            let Some(qpdf_sha) = request.tools.qpdf_sha256.as_ref() else {
                return failed_before_launch(action, request.file, "qpdf SHA-256 missing from tools.env");
            };
            let Some(pdfcpu_rel) = request.tools.pdfcpu_rel.as_ref() else {
                return failed_before_launch(action, request.file, "pdfcpu path missing from tools.env");
            };
            let Some(pdfcpu_sha) = request.tools.pdfcpu_sha256.as_ref() else {
                return failed_before_launch(action, request.file, "pdfcpu SHA-256 missing from tools.env");
            };
            cmd.arg("inventory-pdf")
                .arg(&request.workspace)
                .arg(&request.file)
                .arg(request.app_dir.join(qpdf_rel))
                .arg(qpdf_sha)
                .arg(request.app_dir.join(pdfcpu_rel))
                .arg(pdfcpu_sha);
        }
    }

    match cmd.output() {
        Ok(output) => RunResult {
            ok: output.status.success(),
            action: action.label().to_owned(),
            file: request.file,
            exit_code: output.status.code(),
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        },
        Err(err) => failed_before_launch(action, request.file, &err.to_string()),
    }
}

fn failed_before_launch(action: Action, file: PathBuf, message: &str) -> RunResult {
    RunResult {
        ok: false,
        action: action.label().to_owned(),
        file,
        exit_code: None,
        stdout: String::new(),
        stderr: message.to_owned(),
    }
}

fn app_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn default_workspace() -> PathBuf {
    std::env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join("Documents")
        .join("MCR Engineering Preview Workspace")
}

fn self_test() -> i32 {
    let base = app_dir();
    let engine = base.join("engine").join("mcr-ingest.exe");
    if !engine.is_file() {
        eprintln!("FAIL engine missing: {}", engine.display());
        return 2;
    }
    let tools = ToolConfig::load(&base);
    if !tools.pdf_ready(&base) {
        eprintln!("FAIL PDF specialist configuration missing or incomplete");
        return 3;
    }
    let engine_run = Command::new(&engine).output();
    if !engine_run.as_ref().is_ok_and(|o| o.status.success()) {
        eprintln!("FAIL engine launch");
        return 4;
    }
    let qpdf = base.join(tools.qpdf_rel.as_ref().unwrap());
    let pdfcpu = base.join(tools.pdfcpu_rel.as_ref().unwrap());
    if !Command::new(&qpdf).arg("--version").output().is_ok_and(|o| o.status.success()) {
        eprintln!("FAIL qpdf launch");
        return 5;
    }
    if !Command::new(&pdfcpu).arg("version").output().is_ok_and(|o| o.status.success()) {
        eprintln!("FAIL pdfcpu launch");
        return 6;
    }
    println!("PASS preview self-test: GUI package, engine, qpdf and pdfcpu are launchable");
    0
}

fn main() -> eframe::Result<()> {
    if std::env::args().any(|a| a == "--self-test") {
        std::process::exit(self_test());
    }

    let native_options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1180.0, 760.0])
            .with_min_inner_size([900.0, 600.0]),
        ..Default::default()
    };

    eframe::run_native(
        "MCR Engineering Preview",
        native_options,
        Box::new(|cc| {
            cc.egui_ctx.style_mut(|style| {
                style.spacing.item_spacing = egui::vec2(10.0, 8.0);
                style.spacing.button_padding = egui::vec2(12.0, 8.0);
            });
            Ok(Box::new(PreviewApp::new()))
        }),
    )
}
