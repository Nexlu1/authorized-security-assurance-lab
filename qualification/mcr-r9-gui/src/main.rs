use iced::widget::{button, column, container, row, rule, scrollable, text, Column, Space};
use iced::{window, Alignment, Element, Length, Size, Theme};
use rusqlite::{Connection, OpenFlags};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

const DB_NAME: &str = "mcr-ingest.sqlite3";

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
    RefreshWorkspace,
    ClearOutput,
}

#[derive(Debug, Clone)]
struct Finding {
    kind: String,
    source: String,
    detail: String,
}

#[derive(Debug, Clone)]
struct AuditRow {
    datetime: String,
    event_type: String,
    outcome: String,
    linked_id: String,
    event_sha256: String,
}

#[derive(Debug, Default)]
struct WorkspaceSnapshot {
    loaded: bool,
    object_count: i64,
    occurrence_count: i64,
    finding_count: i64,
    audit_count: i64,
    findings: Vec<Finding>,
    audit: Vec<AuditRow>,
    error: Option<String>,
}

struct App {
    page: Page,
    workspace: Option<PathBuf>,
    selected_file: Option<PathBuf>,
    engine_path: Option<PathBuf>,
    status: String,
    output: String,
    snapshot: WorkspaceSnapshot,
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
            snapshot: WorkspaceSnapshot::default(),
        }
    }
}

impl App {
    fn update(&mut self, message: Message) {
        match message {
            Message::Navigate(page) => {
                self.page = page;
                if self.workspace.is_some() && page != Page::Evidence {
                    self.refresh_workspace();
                }
            }
            Message::ChooseWorkspace => {
                if let Some(path) = rfd::FileDialog::new()
                    .set_title("Choose MCR workspace")
                    .pick_folder()
                {
                    self.workspace = Some(path.clone());
                    self.status = format!("Workspace selected: {}", path.display());
                    self.refresh_workspace();
                }
            }
            Message::ChooseEvidence => {
                if let Some(path) = rfd::FileDialog::new()
                    .set_title("Choose evidence file")
                    .pick_file()
                {
                    self.status = format!("Evidence selected: {}", path.display());
                    self.selected_file = Some(path);
                    self.page = Page::Evidence;
                }
            }
            Message::InitializeWorkspace => self.initialize_workspace(),
            Message::RunInspection => self.run_inspection(),
            Message::RefreshWorkspace => self.refresh_workspace(),
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
            Space::new().width(Length::Fill),
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
            Space::new().height(Length::Fill),
            rule::horizontal(1),
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
            rule::horizontal(1),
            row![
                container(sidebar)
                    .width(Length::Fixed(220.0))
                    .height(Length::Fill),
                container(body)
                    .padding(22)
                    .width(Length::Fill)
                    .height(Length::Fill),
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
        let control = button(text(label))
            .width(Length::Fill)
            .on_press(Message::Navigate(page));
        if self.page == page {
            control.style(iced::widget::button::primary)
        } else {
            control.style(iced::widget::button::text)
        }
    }

    fn overview(&self) -> Element<'_, Message> {
        let workspace = self
            .workspace
            .as_deref()
            .map(display_path)
            .unwrap_or_else(|| "No workspace selected".to_owned());
        let engine = self
            .engine_path
            .as_deref()
            .map(display_path)
            .unwrap_or_else(|| "Not bundled in this development build".to_owned());

        let authority_cards = row![
            metric_card(
                "Authority objects",
                snapshot_number(self.snapshot.loaded, self.snapshot.object_count),
                "SHA-256 content identities",
            ),
            metric_card(
                "Occurrences",
                snapshot_number(self.snapshot.loaded, self.snapshot.occurrence_count),
                "Separate evidential observations",
            ),
            metric_card(
                "Findings",
                snapshot_number(self.snapshot.loaded, self.snapshot.finding_count),
                "Current warnings / state signals",
            ),
            metric_card(
                "Audit events",
                snapshot_number(self.snapshot.loaded, self.snapshot.audit_count),
                "Hash-chained engine events",
            ),
        ]
        .spacing(12);

        let assurance_cards = row![
            metric_card("Target Windows", "PASS".to_owned(), "Earlier real-PC 19/19 gate"),
            metric_card("Hostile matrix", "57 / 57".to_owned(), "Functional adversarial coverage"),
            metric_card("Build route", "CONTROLLED".to_owned(), "Pinned Windows toolchains"),
            metric_card("Ingest network", "OFF".to_owned(), "Local evidence path"),
        ]
        .spacing(12);

        let db_state: Element<'_, Message> = if let Some(error) = &self.snapshot.error {
            container(
                column![
                    text("Workspace authority not loaded").size(15),
                    text(error.as_str()).size(12),
                ]
                .spacing(5),
            )
            .padding(12)
            .style(iced::widget::container::rounded_box)
            .into()
        } else if self.snapshot.loaded {
            container(
                column![
                    text("Workspace authority loaded read-only").size(15),
                    text("The GUI reads the engine's existing SQLite authority; it does not create a second findings or audit store.").size(12),
                ]
                .spacing(5),
            )
            .padding(12)
            .style(iced::widget::container::rounded_box)
            .into()
        } else {
            container(text("Choose or initialize a workspace to load authority data.").size(12))
                .padding(12)
                .style(iced::widget::container::rounded_box)
                .into()
        };

        column![
            text("Overview").size(24),
            text("A human-facing shell around the existing provenance-first ingestion engine.").size(14),
            Space::new().height(Length::Fixed(10.0)),
            text("Workspace authority").size(16),
            authority_cards,
            Space::new().height(Length::Fixed(12.0)),
            db_state,
            Space::new().height(Length::Fixed(14.0)),
            text("Engineering assurance").size(16),
            assurance_cards,
            Space::new().height(Length::Fixed(16.0)),
            rule::horizontal(1),
            Space::new().height(Length::Fixed(12.0)),
            text("Current workspace").size(16),
            text(workspace).size(13),
            row![
                button(text("Choose workspace"))
                    .style(iced::widget::button::primary)
                    .on_press(Message::ChooseWorkspace),
                button(text("Initialize workspace"))
                    .style(iced::widget::button::secondary)
                    .on_press_maybe(
                        self.can_initialize()
                            .then_some(Message::InitializeWorkspace)
                    ),
                button(text("Refresh"))
                    .style(iced::widget::button::subtle)
                    .on_press_maybe(
                        self.workspace
                            .is_some()
                            .then_some(Message::RefreshWorkspace)
                    ),
            ]
            .spacing(10),
            Space::new().height(Length::Fixed(12.0)),
            text("Engine").size(16),
            text(engine).size(13),
            text(self.status.as_str()).size(13),
        ]
        .spacing(8)
        .into()
    }

    fn evidence(&self) -> Element<'_, Message> {
        let selected = self
            .selected_file
            .as_deref()
            .map(display_path)
            .unwrap_or_else(|| "No evidence file selected".to_owned());
        let route = self
            .selected_file
            .as_deref()
            .map(route_for)
            .unwrap_or("Select a file to determine the existing engine route");
        let run_enabled =
            self.workspace.is_some() && self.selected_file.is_some() && self.engine_path.is_some();

        column![
            text("Evidence").size(24),
            text("Choose a local file. The GUI routes it to the existing engine; it does not reimplement parser logic.").size(14),
            Space::new().height(Length::Fixed(8.0)),
            row![
                button(text("Choose evidence file"))
                    .style(iced::widget::button::primary)
                    .on_press(Message::ChooseEvidence),
                button(text("Run current engine"))
                    .style(iced::widget::button::success)
                    .on_press_maybe(run_enabled.then_some(Message::RunInspection)),
            ]
            .spacing(10),
            Space::new().height(Length::Fixed(8.0)),
            container(
                column![
                    text("Selected file").size(15),
                    text(selected).size(13),
                    Space::new().height(Length::Fixed(5.0)),
                    text("Planned engine route").size(15),
                    text(route).size(13),
                ]
                .spacing(4),
            )
            .padding(14)
            .style(iced::widget::container::rounded_box),
            Space::new().height(Length::Fixed(12.0)),
            row![
                text("Engine output").size(16),
                Space::new().width(Length::Fill),
                button(text("Clear"))
                    .style(iced::widget::button::subtle)
                    .on_press(Message::ClearOutput)
            ],
            container(
                scrollable(
                    text(if self.output.is_empty() {
                        "No run output yet."
                    } else {
                        self.output.as_str()
                    })
                    .size(13)
                )
                .height(Length::Fill)
            )
            .padding(12)
            .height(Length::Fill)
            .style(iced::widget::container::rounded_box),
        ]
        .spacing(8)
        .height(Length::Fill)
        .into()
    }

    fn findings(&self) -> Element<'_, Message> {
        let mut list = Column::new().spacing(8);
        if self.snapshot.findings.is_empty() {
            list = list.push(
                container(text(if self.snapshot.loaded {
                    "No warning/state rows are currently present in the loaded workspace."
                } else {
                    "Choose a workspace to load engine-produced findings."
                }))
                .padding(14)
                .style(iced::widget::container::rounded_box),
            );
        } else {
            for finding in &self.snapshot.findings {
                list = list.push(finding_card(finding));
            }
        }

        column![
            row![
                column![
                    text("Findings").size(24),
                    text("Read-only view of warnings and state signals already produced by the engine.").size(14),
                ],
                Space::new().width(Length::Fill),
                button(text("Refresh"))
                    .style(iced::widget::button::subtle)
                    .on_press_maybe(
                        self.workspace
                            .is_some()
                            .then_some(Message::RefreshWorkspace)
                    ),
            ]
            .align_y(Alignment::Center),
            text(format!(
                "{} current warning/state rows across archive, mail, PDF and OOXML controls",
                self.snapshot.finding_count
            ))
            .size(13),
            Space::new().height(Length::Fixed(8.0)),
            scrollable(list).height(Length::Fill),
        ]
        .spacing(8)
        .height(Length::Fill)
        .into()
    }

    fn audit(&self) -> Element<'_, Message> {
        let mut list = Column::new().spacing(8);
        if self.snapshot.audit.is_empty() {
            list = list.push(
                container(text(if self.snapshot.loaded {
                    "No audit events are currently present in the loaded workspace."
                } else {
                    "Choose a workspace to load the engine's audit chain."
                }))
                .padding(14)
                .style(iced::widget::container::rounded_box),
            );
        } else {
            for event in &self.snapshot.audit {
                list = list.push(audit_card(event));
            }
        }

        column![
            row![
                column![
                    text("Audit").size(24),
                    text("Latest hash-chained engine events from the existing workspace authority.").size(14),
                ],
                Space::new().width(Length::Fill),
                button(text("Refresh"))
                    .style(iced::widget::button::subtle)
                    .on_press_maybe(
                        self.workspace
                            .is_some()
                            .then_some(Message::RefreshWorkspace)
                    ),
            ]
            .align_y(Alignment::Center),
            text(format!("{} audit events recorded in the workspace", self.snapshot.audit_count))
                .size(13),
            Space::new().height(Length::Fixed(8.0)),
            scrollable(list).height(Length::Fill),
        ]
        .spacing(8)
        .height(Length::Fill)
        .into()
    }

    fn can_initialize(&self) -> bool {
        self.workspace.is_some() && self.engine_path.is_some()
    }

    fn refresh_workspace(&mut self) {
        let Some(workspace) = self.workspace.as_deref() else {
            self.snapshot = WorkspaceSnapshot::default();
            return;
        };
        self.snapshot = match load_workspace_snapshot(workspace) {
            Ok(snapshot) => snapshot,
            Err(error) => WorkspaceSnapshot {
                error: Some(error),
                ..WorkspaceSnapshot::default()
            },
        };
    }

    fn initialize_workspace(&mut self) {
        let (Some(engine), Some(workspace)) = (&self.engine_path, &self.workspace) else {
            self.status = "Choose a workspace and bundle the engine first.".to_owned();
            return;
        };
        self.capture_process(Command::new(engine).arg("init").arg(workspace));
        self.refresh_workspace();
    }

    fn run_inspection(&mut self) {
        let (Some(engine), Some(workspace), Some(file)) =
            (&self.engine_path, &self.workspace, &self.selected_file)
        else {
            self.status = "Engine, workspace and evidence file are all required.".to_owned();
            return;
        };

        let extension = file
            .extension()
            .and_then(|s| s.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
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

        self.capture_process(
            Command::new(engine)
                .arg(command_name)
                .arg(workspace)
                .arg(file),
        );
        self.refresh_workspace();
    }

    fn capture_process(&mut self, command: &mut Command) {
        match command.output() {
            Ok(result) => {
                let stdout = String::from_utf8_lossy(&result.stdout);
                let stderr = String::from_utf8_lossy(&result.stderr);
                self.output = format!(
                    "Exit: {}\n\nSTDOUT\n{}\n\nSTDERR\n{}",
                    result.status, stdout, stderr
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

fn metric_card(
    title: &'static str,
    value: String,
    note: &'static str,
) -> Element<'static, Message> {
    container(
        column![
            text(title).size(12),
            text(value).size(20),
            text(note).size(11),
        ]
        .spacing(4),
    )
    .padding(14)
    .width(Length::FillPortion(1))
    .style(iced::widget::container::rounded_box)
    .into()
}

fn finding_card<'a>(finding: &'a Finding) -> Element<'a, Message> {
    container(
        column![
            row![
                text(finding.kind.as_str()).size(15),
                Space::new().width(Length::Fill),
                text(short_id(&finding.source)).size(11),
            ],
            text(finding.detail.as_str()).size(12),
        ]
        .spacing(5),
    )
    .padding(12)
    .width(Length::Fill)
    .style(iced::widget::container::rounded_box)
    .into()
}

fn audit_card<'a>(event: &'a AuditRow) -> Element<'a, Message> {
    container(
        column![
            row![
                text(event.event_type.as_str()).size(15),
                Space::new().width(Length::Fill),
                text(event.outcome.as_str()).size(12),
            ],
            text(event.datetime.as_str()).size(11),
            text(format!(
                "Linked: {} · Event SHA-256: {}",
                if event.linked_id.is_empty() {
                    "—"
                } else {
                    event.linked_id.as_str()
                },
                short_id(&event.event_sha256)
            ))
            .size(11),
        ]
        .spacing(4),
    )
    .padding(12)
    .width(Length::Fill)
    .style(iced::widget::container::rounded_box)
    .into()
}

fn snapshot_number(loaded: bool, value: i64) -> String {
    if loaded {
        value.to_string()
    } else {
        "—".to_owned()
    }
}

fn short_id(value: &str) -> String {
    if value.len() > 18 {
        format!("{}…", &value[..18])
    } else {
        value.to_owned()
    }
}

fn load_workspace_snapshot(workspace: &Path) -> Result<WorkspaceSnapshot, String> {
    let db_path = workspace.join(DB_NAME);
    if !db_path.is_file() {
        return Err(format!(
            "No {} exists in the selected workspace yet.",
            DB_NAME
        ));
    }

    let flags = OpenFlags::SQLITE_OPEN_READ_ONLY | OpenFlags::SQLITE_OPEN_NO_MUTEX;
    let conn = Connection::open_with_flags(&db_path, flags).map_err(|error| error.to_string())?;
    conn.busy_timeout(Duration::from_millis(750))
        .map_err(|error| error.to_string())?;

    let object_count = count(&conn, "SELECT COUNT(*) FROM blob_object")?;
    let occurrence_count = count(&conn, "SELECT COUNT(*) FROM occurrence")?;
    let audit_count = count(&conn, "SELECT COUNT(*) FROM audit_event")?;
    let archive_blocks = count(
        &conn,
        "SELECT COUNT(*) FROM archive_member WHERE policy_status='BLOCK_MATERIALISATION'",
    )?;
    let mail_warnings = count(
        &conn,
        "SELECT COUNT(*) FROM mail_message WHERE parser_note IS NOT NULL OR duplicate_message_id=1 OR duplicate_message_id_conflict=1 OR thread_cycle=1",
    )?;
    let pdf_signals = count(&conn, "SELECT COUNT(*) FROM pdf_signal")?;
    let ooxml_signals = count(&conn, "SELECT COUNT(*) FROM ooxml_signal")?;
    let finding_count = archive_blocks
        .checked_add(mail_warnings)
        .and_then(|value| value.checked_add(pdf_signals))
        .and_then(|value| value.checked_add(ooxml_signals))
        .ok_or_else(|| "finding count overflow".to_owned())?;

    Ok(WorkspaceSnapshot {
        loaded: true,
        object_count,
        occurrence_count,
        finding_count,
        audit_count,
        findings: load_findings(&conn).map_err(|error| error.to_string())?,
        audit: load_audit(&conn).map_err(|error| error.to_string())?,
        error: None,
    })
}

fn count(conn: &Connection, sql: &str) -> Result<i64, String> {
    conn.query_row(sql, [], |row| row.get(0))
        .map_err(|error| error.to_string())
}

fn load_findings(conn: &Connection) -> rusqlite::Result<Vec<Finding>> {
    let mut findings = Vec::new();

    {
        let mut stmt = conn.prepare(
            "SELECT archive_sha256,name_text,policy_reasons_json
             FROM archive_member
             WHERE policy_status='BLOCK_MATERIALISATION'
             ORDER BY id DESC LIMIT 20",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(Finding {
                kind: "Archive blocked".to_owned(),
                source: row.get(0)?,
                detail: format!("{} · {}", row.get::<_, String>(1)?, row.get::<_, String>(2)?),
            })
        })?;
        for row in rows {
            findings.push(row?);
        }
    }

    {
        let mut stmt = conn.prepare(
            "SELECT source_sha256,COALESCE(subject,'(no subject)'),parser_note,
                    duplicate_message_id,duplicate_message_id_conflict,thread_cycle
             FROM mail_message
             WHERE parser_note IS NOT NULL OR duplicate_message_id=1
                OR duplicate_message_id_conflict=1 OR thread_cycle=1
             ORDER BY id DESC LIMIT 20",
        )?;
        let rows = stmt.query_map([], |row| {
            let subject: String = row.get(1)?;
            let note: Option<String> = row.get(2)?;
            let duplicate: i64 = row.get(3)?;
            let conflict: i64 = row.get(4)?;
            let cycle: i64 = row.get(5)?;
            let mut flags = Vec::new();
            if duplicate != 0 {
                flags.push("duplicate Message-ID");
            }
            if conflict != 0 {
                flags.push("conflicting duplicate Message-ID");
            }
            if cycle != 0 {
                flags.push("thread cycle");
            }
            let mut detail = subject;
            if let Some(note) = note {
                detail.push_str(" · ");
                detail.push_str(&note);
            }
            if !flags.is_empty() {
                detail.push_str(" · ");
                detail.push_str(&flags.join(", "));
            }
            Ok(Finding {
                kind: "Mail provenance warning".to_owned(),
                source: row.get(0)?,
                detail,
            })
        })?;
        for row in rows {
            findings.push(row?);
        }
    }

    {
        let mut stmt = conn.prepare(
            "SELECT source_sha256,signal,signal_count
             FROM pdf_signal ORDER BY source_sha256,signal LIMIT 20",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(Finding {
                kind: "PDF state signal".to_owned(),
                source: row.get(0)?,
                detail: format!("{} · count {}", row.get::<_, String>(1)?, row.get::<_, i64>(2)?),
            })
        })?;
        for row in rows {
            findings.push(row?);
        }
    }

    {
        let mut stmt = conn.prepare(
            "SELECT source_sha256,part_name,signal,signal_count
             FROM ooxml_signal ORDER BY source_sha256,part_name,signal LIMIT 20",
        )?;
        let rows = stmt.query_map([], |row| {
            Ok(Finding {
                kind: "OOXML state signal".to_owned(),
                source: row.get(0)?,
                detail: format!(
                    "{} · {} · count {}",
                    row.get::<_, String>(1)?,
                    row.get::<_, String>(2)?,
                    row.get::<_, i64>(3)?
                ),
            })
        })?;
        for row in rows {
            findings.push(row?);
        }
    }

    Ok(findings)
}

fn load_audit(conn: &Connection) -> rusqlite::Result<Vec<AuditRow>> {
    let mut stmt = conn.prepare(
        "SELECT event_datetime,event_type,outcome,COALESCE(linked_id,''),current_event_sha256
         FROM audit_event ORDER BY id DESC LIMIT 100",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok(AuditRow {
            datetime: row.get(0)?,
            event_type: row.get(1)?,
            outcome: row.get(2)?,
            linked_id: row.get(3)?,
            event_sha256: row.get(4)?,
        })
    })?;
    rows.collect()
}

fn locate_engine() -> Option<PathBuf> {
    let exe = std::env::current_exe().ok()?;
    let dir = exe.parent()?;
    [
        dir.join("mcr-ingest.exe"),
        dir.join("engine").join("mcr-ingest.exe"),
    ]
    .into_iter()
    .find(|candidate| candidate.is_file())
}

fn route_for(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
        "zip" => "ZIP → inventory-zip (inventory/blocking policy; no blind extraction)",
        "eml" => "EML → index-eml (raw source authority + derivative parse)",
        "mbox" => "MBOX → index-mbox (byte-range provenance + ambiguity controls)",
        "csv" => "CSV → index-csv (byte/line provenance; no spreadsheet execution)",
        "docx" | "xlsx" | "pptx" => {
            "OOXML → inventory-ooxml (package/state inventory; no blind extraction)"
        }
        "pdf" => {
            "PDF → generic capture in this GUI preview; qpdf/pdfcpu wiring follows in the packaging slice"
        }
        _ => "Other → ingest-file (SHA-256 content-addressed capture + occurrence provenance)",
    }
}

fn display_path(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn snapshot_reads_authority_without_mutating_database() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let workspace = std::env::temp_dir().join(format!(
            "mcr-r9-gui-test-{}-{unique}",
            std::process::id()
        ));
        fs::create_dir_all(&workspace).expect("create workspace");
        let db_path = workspace.join(DB_NAME);

        {
            let conn = Connection::open(&db_path).expect("create synthetic db");
            conn.execute_batch(
                "
                CREATE TABLE blob_object(sha256 TEXT PRIMARY KEY);
                CREATE TABLE occurrence(id INTEGER PRIMARY KEY);
                CREATE TABLE audit_event(
                    id INTEGER PRIMARY KEY,
                    event_datetime TEXT,
                    event_type TEXT,
                    outcome TEXT,
                    linked_id TEXT,
                    current_event_sha256 TEXT
                );
                CREATE TABLE archive_member(
                    id INTEGER PRIMARY KEY,
                    archive_sha256 TEXT,
                    name_text TEXT,
                    policy_status TEXT,
                    policy_reasons_json TEXT
                );
                CREATE TABLE mail_message(
                    id INTEGER PRIMARY KEY,
                    source_sha256 TEXT,
                    subject TEXT,
                    parser_note TEXT,
                    duplicate_message_id INTEGER,
                    duplicate_message_id_conflict INTEGER,
                    thread_cycle INTEGER
                );
                CREATE TABLE pdf_signal(source_sha256 TEXT,signal TEXT,signal_count INTEGER);
                CREATE TABLE ooxml_signal(
                    source_sha256 TEXT,
                    part_name TEXT,
                    signal TEXT,
                    signal_count INTEGER
                );
                INSERT INTO blob_object VALUES('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa');
                INSERT INTO occurrence VALUES(1);
                INSERT INTO audit_event VALUES(
                    1,'2026-09-07T07:00:00Z','ingestion','PASS',
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
                );
                INSERT INTO archive_member VALUES(
                    1,
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    '../outside.txt','BLOCK_MATERIALISATION','[\"parent_traversal\"]'
                );
                INSERT INTO mail_message VALUES(
                    1,
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'Synthetic warning','raw ambiguity retained',1,1,0
                );
                INSERT INTO pdf_signal VALUES(
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'action:JavaScript',1
                );
                INSERT INTO ooxml_signal VALUES(
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'word/document.xml','word:hidden_text_vanish',1
                );
                ",
            )
            .expect("seed synthetic authority");
        }

        let before = fs::read(&db_path).expect("read database before");
        let snapshot = load_workspace_snapshot(&workspace).expect("load snapshot");
        let after = fs::read(&db_path).expect("read database after");

        assert!(snapshot.loaded);
        assert_eq!(snapshot.object_count, 1);
        assert_eq!(snapshot.occurrence_count, 1);
        assert_eq!(snapshot.audit_count, 1);
        assert_eq!(snapshot.finding_count, 4);
        assert_eq!(snapshot.findings.len(), 4);
        assert_eq!(snapshot.audit.len(), 1);
        assert_eq!(before, after, "read-only GUI must not mutate authority bytes");

        fs::remove_dir_all(workspace).expect("clean synthetic workspace");
    }
}
