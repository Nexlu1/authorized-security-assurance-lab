use iced::widget::{button, column, container, horizontal_rule, row, scrollable, text, Space};
use iced::{window, Alignment, Element, Length, Size, Theme};
use std::path::{Path, PathBuf};
use std::process::Command;

pub fn main() -> iced::Result {
    iced::application(App::default, App::update, App::view)
        .theme(Theme::Light)
        .window(window::Settings {
            size: Size::new(1240.0, 780.0),
            min_size: Some(Size::new(960.0, 640.0)),
            ..Default::default()
        })
        .run()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Page {
    Overview,
    Evidence,
    Findings,
    Audit,
}

impl Page {
    fn label(self) -> &'static str {
        match self {
            Self::Overview => "Overview",
            Self::Evidence => "Evidence",
            Self::Findings => "Findings",
            Self::Audit => "Audit",
        }
    }
}

#[derive(Debug, Clone)]
enum Message {
    Navigate(Page),
    ChooseWorkspace,
    ChooseEvidence,
    InitializeWorkspace,
    RunInspection,
    ClearOutput,
}

struct App {
    page: Page,
    workspace: Option<PathBuf>,
    selected_file: Option<PathBuf>,
    engine_path: Option<PathBuf>,
    status: String,
    output: String,
}

impl Default for App {
    fn default() -> Self {
        let engine_path = locate_engine();
        let status = match &engine_path {
            Some(path) => format!("Engine detected: {}", path.display()),
            None => "GUI ready. Engine binary is not bundled with this development build yet.".to_owned(),
        };
        Self {
            page: Page::Overview,
            workspace: None,
            selected_file: None,
            engine_path,
            status,
            output: String::new(),
        }
    }
}

impl App {
    fn update(&mut self, message: Message) {
        match message {
            Message::Navigate(page) => self.page = page,
            Message::ChooseWorkspace => {
                if let Some(path) = rfd::FileDialog::new().set_title("Choose MCR workspace").pick_folder() {
                    self.status = format!("Workspace selected: {}", path.display());
                    self.workspace = Some(path);
                }
            }
            Message::ChooseEvidence => {
                if let Some(path) = rfd::FileDialog::new().set_title("Choose evidence file").pick_file() {
                    self.status = format!("Evidence selected: {}", path.display());
                    self.selected_file = Some(path);
                    self.page = Page::Evidence;
                }
            }
            Message::InitializeWorkspace => self.initialize_workspace(),
            Message::RunInspection => self.run_inspection(),
            Message::ClearOutput => self.output.clear(),
        }
    }

    fn view(&self) -> Element<'_, Message> {
        let header = row![
            column![
                text("MCR Evidence Tooling").size(28),
                text("Engineering Preview · local/offline evidence workflow").size(14),
            ]
            .spacing(3),
            Space::with_width(Length::Fill),
            column![
                text("ENGINE QUALIFICATION").size(11),
                text("57 / 57 hostile cases").size(16),
            ]
            .align_x(Alignment::End),
        ]
        .align_y(Alignment::Center)
        .padding([18, 22]);

        let sidebar = column![
            text("WORKSPACE").size(11),
            self.nav_button(Page::Overview),
            self.nav_button(Page::Evidence),
            self.nav_button(Page::Findings),
            self.nav_button(Page::Audit),
            Space::with_height(Length::Fill),
            horizontal_rule(1),
            text("Frozen MCR R59: unchanged").size(12),
            text("Network during ingest: off").size(12),
        ]
        .spacing(10)
        .padding(16)
        .height(Length::Fill);

        let body = match self.page {
            Page::Overview => self.overview(),
            Page::Evidence => self.evidence(),
            Page::Findings => self.findings(),
            Page::Audit => self.audit(),
        };

        column![
            header,
            horizontal_rule(1),
            row![
                container(sidebar).width(Length::Fixed(220.0)).height(Length::Fill),
                container(body).padding(22).width(Length::Fill).height(Length::Fill),
            ]
            .height(Length::Fill),
        ]
        .height(Length::Fill)
        .into()
    }

    fn nav_button(&self, page: Page) -> iced::widget::Button<'_, Message> {
        let label = if self.page == page {
            format!("●  {}", page.label())
        } else {
            format!("    {}", page.label())
        };
        button(text(label)).width(Length::Fill).on_press(Message::Navigate(page))
    }

    fn overview(&self) -> Element<'_, Message> {
        let workspace = self.workspace.as_deref().map(display_path).unwrap_or_else(|| "No workspace selected".to_owned());
        let engine = self.engine_path.as_deref().map(display_path).unwrap_or_else(|| "Not bundled in this development build".to_owned());

        let cards = row![
            self.metric_card("Target Windows", "PASS", "Earlier real-PC 19/19 gate"),
            self.metric_card("Hostile matrix", "57 / 57", "Functional adversarial coverage"),
            self.metric_card("Build route", "REPRODUCIBLE", "Pinned GNU-LLVM Windows route"),
            self.metric_card("Ingest network", "OFF", "Local evidence path"),
        ]
        .spacing(12);

        column![
            text("Overview").size(24),
            text("A human-facing shell around the existing provenance-first ingestion engine.").size(14),
            Space::with_height(Length::Fixed(10.0)),
            cards,
            Space::with_height(Length::Fixed(16.0)),
            horizontal_rule(1),
            Space::with_height(Length::Fixed(12.0)),
            text("Current workspace").size(16),
            text(workspace).size(13),
            row![
                button(text("Choose workspace")).on_press(Message::ChooseWorkspace),
                button(text("Initialize workspace")).on_press_maybe(self.can_initialize().then_some(Message::InitializeWorkspace)),
            ]
            .spacing(10),
            Space::with_height(Length::Fixed(12.0)),
            text("Engine").size(16),
            text(engine).size(13),
            text(self.status.as_str()).size(13),
        ]
        .spacing(8)
        .into()
    }

    fn evidence(&self) -> Element<'_, Message> {
        let selected = self.selected_file.as_deref().map(display_path).unwrap_or_else(|| "No evidence file selected".to_owned());
        let route = self.selected_file.as_deref().map(route_for).unwrap_or("Select a file to determine the existing engine route");
        let run_enabled = self.workspace.is_some() && self.selected_file.is_some() && self.engine_path.is_some();

        column![
            text("Evidence").size(24),
            text("Choose a local file. The GUI routes it to the existing engine; it does not reimplement parser logic.").size(14),
            Space::with_height(Length::Fixed(8.0)),
            button(text("Choose evidence file")).on_press(Message::ChooseEvidence),
            Space::with_height(Length::Fixed(8.0)),
            text("Selected file").size(15),
            text(selected).size(13),
            text("Planned engine route").size(15),
            text(route).size(13),
            Space::with_height(Length::Fixed(8.0)),
            button(text("Run current engine")).on_press_maybe(run_enabled.then_some(Message::RunInspection)),
            Space::with_height(Length::Fixed(12.0)),
            row![text("Engine output").size(16), Space::with_width(Length::Fill), button(text("Clear")).on_press(Message::ClearOutput)],
            container(scrollable(text(if self.output.is_empty() { "No run output yet." } else { self.output.as_str() }).size(13)).height(Length::Fill))
                .padding(12)
                .height(Length::Fill),
        ]
        .spacing(8)
        .height(Length::Fill)
        .into()
    }

    fn findings(&self) -> Element<'_, Message> {
        column![
            text("Findings").size(24),
            text("This surface will present engine-produced warnings and state signals in plain language.").size(14),
            Space::with_height(Length::Fixed(12.0)),
            text("Current rule").size(16),
            text("The GUI must not invent findings independently of the engine or silently downgrade validation failures.").size(13),
            Space::with_height(Length::Fixed(12.0)),
            text("Next slice").size(16),
            text("Read structured findings from the workspace authority database and link each item back to its source SHA-256/occurrence.").size(13),
        ]
        .spacing(8)
        .into()
    }

    fn audit(&self) -> Element<'_, Message> {
        column![
            text("Audit").size(24),
            text("The engine already writes hash-chained audit events. The GUI will expose that existing authority rather than create a second audit system.").size(14),
            Space::with_height(Length::Fixed(12.0)),
            text("Current status").size(16),
            text("Audit display wiring is the next GUI data-binding slice after this shell compiles on both Windows CI targets.").size(13),
        ]
        .spacing(8)
        .into()
    }

    fn metric_card<'a>(&self, title: &'a str, value: &'a str, note: &'a str) -> Element<'a, Message> {
        container(column![text(title).size(12), text(value).size(19), text(note).size(11)].spacing(4))
            .padding(14)
            .width(Length::FillPortion(1))
            .into()
    }

    fn can_initialize(&self) -> bool {
        self.workspace.is_some() && self.engine_path.is_some()
    }

    fn initialize_workspace(&mut self) {
        let (Some(engine), Some(workspace)) = (&self.engine_path, &self.workspace) else {
            self.status = "Choose a workspace and bundle the engine first.".to_owned();
            return;
        };
        self.capture_process(Command::new(engine).arg("init").arg(workspace));
    }

    fn run_inspection(&mut self) {
        let (Some(engine), Some(workspace), Some(file)) = (&self.engine_path, &self.workspace, &self.selected_file) else {
            self.status = "Engine, workspace and evidence file are all required.".to_owned();
            return;
        };

        let extension = file.extension().and_then(|s| s.to_str()).unwrap_or("").to_ascii_lowercase();
        let command_name = match extension.as_str() {
            "zip" => "inventory-zip",
            "eml" => "index-eml",
            "mbox" => "index-mbox",
            "csv" => "index-csv",
            "docx" | "xlsx" | "pptx" => "inventory-ooxml",
            "pdf" => "ingest-file",
            _ => "ingest-file",
        };

        if extension == "pdf" {
            self.status = "PDF bytes will be captured now; qpdf/pdfcpu state inventory is deliberately not wired into this GUI preview yet.".to_owned();
        }

        self.capture_process(Command::new(engine).arg(command_name).arg(workspace).arg(file));
    }

    fn capture_process(&mut self, command: &mut Command) {
        match command.output() {
            Ok(result) => {
                let stdout = String::from_utf8_lossy(&result.stdout);
                let stderr = String::from_utf8_lossy(&result.stderr);
                self.output = format!(
                    "Exit: {}\n\nSTDOUT\n{}\n\nSTDERR\n{}",
                    result.status,
                    stdout,
                    stderr
                );
                self.status = if result.status.success() {
                    "Engine run completed successfully.".to_owned()
                } else {
                    "Engine run returned a failure. Exact output is shown below.".to_owned()
                };
            }
            Err(error) => {
                self.output = format!("Failed to launch engine: {error}");
                self.status = "Engine launch failed.".to_owned();
            }
        }
    }
}

fn locate_engine() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    for candidate in [dir.join("mcr-ingest.exe"), dir.join("engine").join("mcr-ingest.exe")] {
        if candidate.is_file() {
            return Some(candidate);
        }
    }
    None
}

fn route_for(path: &Path) -> &'static str {
    match path.extension().and_then(|s| s.to_str()).unwrap_or("").to_ascii_lowercase().as_str() {
        "zip" => "ZIP → inventory-zip (inventory/blocking policy; no blind extraction)",
        "eml" => "EML → index-eml (raw source authority + derivative parse)",
        "mbox" => "MBOX → index-mbox (byte-range provenance + ambiguity controls)",
        "csv" => "CSV → index-csv (byte/line provenance; no spreadsheet execution)",
        "docx" | "xlsx" | "pptx" => "OOXML → inventory-ooxml (package/state inventory; no blind extraction)",
        "pdf" => "PDF → generic capture in this GUI preview; qpdf/pdfcpu wiring follows in the packaging slice",
        _ => "Other → ingest-file (SHA-256 content-addressed capture + occurrence provenance)",
    }
}

fn display_path(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}
