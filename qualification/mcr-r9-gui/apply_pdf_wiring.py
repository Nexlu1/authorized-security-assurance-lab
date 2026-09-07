from __future__ import annotations

from pathlib import Path

p = Path("qualification/mcr-r9-gui/src/main.rs")
text = p.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one target, found {count}")
    text = text.replace(old, new)

replace_once(
    'const DB_NAME: &str = "mcr-ingest.sqlite3";\n',
    '''const DB_NAME: &str = "mcr-ingest.sqlite3";\nconst QPDF_SHA256: &str = "57c003e868fb66cd343fd5afb91be8c2277f56434eea8635762499731bf9f60d";\nconst PDFCPU_SHA256: &str = "94cafb66b508c2eb8648dffbb17fddb74b7a117fdc38846e36f9ec6322bdd05e";\n''',
    "specialist hash constants",
)
replace_once(
    '''    engine_path: Option<PathBuf>,\n    status: String,\n''',
    '''    engine_path: Option<PathBuf>,\n    qpdf_path: Option<PathBuf>,\n    pdfcpu_path: Option<PathBuf>,\n    status: String,\n''',
    "app specialist fields",
)
replace_once(
    '''        let engine_path = locate_engine();\n        let status = match &engine_path {\n''',
    '''        let engine_path = locate_engine();\n        let qpdf_path = locate_qpdf();\n        let pdfcpu_path = locate_pdfcpu();\n        let status = match &engine_path {\n''',
    "default specialist discovery",
)
replace_once(
    '''            selected_file: None,\n            engine_path,\n            status,\n''',
    '''            selected_file: None,\n            engine_path,\n            qpdf_path,\n            pdfcpu_path,\n            status,\n''',
    "default specialist fields",
)
replace_once(
    '''        let run_enabled = !self.busy\n            && self.workspace.is_some()\n            && self.selected_file.is_some()\n            && self.engine_path.is_some();\n''',
    '''        let selected_is_pdf = self\n            .selected_file\n            .as_deref()\n            .and_then(|path| path.extension())\n            .and_then(|value| value.to_str())\n            .is_some_and(|value| value.eq_ignore_ascii_case("pdf"));\n        let specialists_ready = self.qpdf_path.is_some() && self.pdfcpu_path.is_some();\n        let run_enabled = !self.busy\n            && self.workspace.is_some()\n            && self.selected_file.is_some()\n            && self.engine_path.is_some()\n            && (!selected_is_pdf || specialists_ready);\n        let specialist_state = if specialists_ready {\n            "PDF specialists ready: qpdf 12.4.1 + pdfcpu 0.15.0 (hash-bound)"\n        } else {\n            "PDF specialists not packaged: PDF analysis is disabled rather than weakened"\n        };\n''',
    "evidence readiness",
)
replace_once(
    '''                    text("Planned engine route").size(15),\n                    text(route).size(13),\n''',
    '''                    text("Planned engine route").size(15),\n                    text(route).size(13),\n                    Space::new().height(Length::Fixed(5.0)),\n                    text("PDF specialist status").size(15),\n                    text(specialist_state).size(13),\n''',
    "visible specialist status",
)
old_run = '''        let command_name = match extension.as_str() {\n            "zip" => "inventory-zip",\n            "eml" => "index-eml",\n            "mbox" => "index-mbox",\n            "csv" => "index-csv",\n            "docx" | "xlsx" | "pptx" => "inventory-ooxml",\n            "pdf" => "ingest-file",\n            _ => "ingest-file",\n        };\n\n        self.busy = true;\n        self.status = if extension == "pdf" {\n            "Capturing PDF bytes… qpdf/pdfcpu state inventory is deliberately not wired into this GUI preview yet.".to_owned()\n        } else {\n            format!("Running {command_name}…")\n        };\n\n        let request = ProcessRequest {\n            program: engine,\n            args: vec![\n                OsString::from(command_name),\n                workspace.as_os_str().to_owned(),\n                file.as_os_str().to_owned(),\n            ],\n            operation: "Evidence inspection",\n        };\n'''
new_run = '''        let (args, operation, status) = if extension == "pdf" {\n            let (Some(qpdf), Some(pdfcpu)) = (self.qpdf_path.clone(), self.pdfcpu_path.clone()) else {\n                self.status = "PDF specialist analysis is unavailable because the packaged qpdf/pdfcpu tools are missing.".to_owned();\n                return Task::none();\n            };\n            (\n                vec![\n                    OsString::from("inventory-pdf"),\n                    workspace.as_os_str().to_owned(),\n                    file.as_os_str().to_owned(),\n                    qpdf.as_os_str().to_owned(),\n                    OsString::from(QPDF_SHA256),\n                    pdfcpu.as_os_str().to_owned(),\n                    OsString::from(PDFCPU_SHA256),\n                ],\n                "PDF specialist inspection",\n                "Running hash-bound qpdf/pdfcpu PDF analysis…".to_owned(),\n            )\n        } else {\n            let command_name = match extension.as_str() {\n                "zip" => "inventory-zip",\n                "eml" => "index-eml",\n                "mbox" => "index-mbox",\n                "csv" => "index-csv",\n                "docx" | "xlsx" | "pptx" => "inventory-ooxml",\n                _ => "ingest-file",\n            };\n            (\n                vec![\n                    OsString::from(command_name),\n                    workspace.as_os_str().to_owned(),\n                    file.as_os_str().to_owned(),\n                ],\n                "Evidence inspection",\n                format!("Running {command_name}…"),\n            )\n        };\n\n        self.busy = true;\n        self.status = status;\n\n        let request = ProcessRequest {\n            program: engine,\n            args,\n            operation,\n        };\n'''
replace_once(old_run, new_run, "run inspection PDF routing")
replace_once(
    '''fn route_for(path: &Path) -> &'static str {\n''',
    '''fn locate_qpdf() -> Option<PathBuf> {\n    locate_packaged_tool(&["tools", "qpdf", "qpdf-12.4.1-msvc64", "bin", "qpdf.exe"])\n}\n\nfn locate_pdfcpu() -> Option<PathBuf> {\n    locate_packaged_tool(&["tools", "pdfcpu", "pdfcpu_0.15.0_Windows_x86_64", "pdfcpu.exe"])\n}\n\nfn locate_packaged_tool(parts: &[&str]) -> Option<PathBuf> {\n    let exe = std::env::current_exe().ok()?;\n    let mut candidate = exe.parent()?.to_path_buf();\n    for part in parts {\n        candidate.push(part);\n    }\n    candidate.is_file().then_some(candidate)\n}\n\nfn route_for(path: &Path) -> &'static str {\n''',
    "tool locators",
)
replace_once(
    '''        "pdf" => {\n            "PDF → generic capture in this GUI preview; qpdf/pdfcpu wiring follows in the packaging slice"\n        }\n''',
    '''        "pdf" => {\n            "PDF → inventory-pdf (qpdf 12.4.1 + pdfcpu 0.15.0; exact hash-bound specialists)"\n        }\n''',
    "visible PDF route",
)
replace_once(
    '''    #[test]\n    fn snapshot_reads_authority_without_mutating_database() {\n''',
    '''    #[test]\n    fn pdf_route_is_specialist_inventory_not_generic_capture() {\n        assert!(route_for(Path::new("synthetic.pdf")).contains("inventory-pdf"));\n        assert!(!route_for(Path::new("synthetic.pdf")).contains("generic capture"));\n        assert_eq!(QPDF_SHA256.len(), 64);\n        assert_eq!(PDFCPU_SHA256.len(), 64);\n    }\n\n    #[test]\n    fn snapshot_reads_authority_without_mutating_database() {\n''',
    "PDF route regression test",
)
p.write_text(text, encoding="utf-8", newline="\n")
print("PASS: wired hash-bound PDF specialists into R9 GUI source")
