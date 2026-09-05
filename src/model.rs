use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    Info,
    Warning,
    High,
    Critical,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Finding {
    pub code: String,
    pub severity: Severity,
    pub message: String,
}

impl Finding {
    pub fn new(code: impl Into<String>, severity: Severity, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            severity,
            message: message.into(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ScanPolicy {
    pub max_file_bytes: u64,
    pub max_archive_entries: usize,
    pub max_archive_total_uncompressed_bytes: u64,
    pub max_archive_entry_ratio: f64,
    pub max_path_depth: usize,
    pub max_segment_bytes: usize,
}

impl Default for ScanPolicy {
    fn default() -> Self {
        Self {
            max_file_bytes: 8 * 1024 * 1024 * 1024,
            max_archive_entries: 100_000,
            max_archive_total_uncompressed_bytes: 64 * 1024 * 1024 * 1024,
            max_archive_entry_ratio: 1_000.0,
            max_path_depth: 64,
            max_segment_bytes: 255,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ArchiveEntryRecord {
    pub name: String,
    pub uncompressed_bytes: u64,
    pub compressed_bytes: u64,
    pub unix_mode: Option<u32>,
    pub findings: Vec<Finding>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ArchiveSummary {
    pub entries_seen: usize,
    pub total_uncompressed_bytes: u64,
    pub total_compressed_bytes: u64,
    pub entries: Vec<ArchiveEntryRecord>,
    pub findings: Vec<Finding>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ItemRecord {
    pub relative_path: String,
    pub object_type: String,
    pub size_bytes: Option<u64>,
    pub sha256: Option<String>,
    pub extension: Option<String>,
    pub detected_kind: Option<String>,
    pub findings: Vec<Finding>,
    pub archive: Option<ArchiveSummary>,
    pub error: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
pub struct ScanSummary {
    pub objects_seen: usize,
    pub regular_files: usize,
    pub directories: usize,
    pub symlinks: usize,
    pub errors: usize,
    pub findings_info: usize,
    pub findings_warning: usize,
    pub findings_high: usize,
    pub findings_critical: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Manifest {
    pub schema_version: String,
    pub tool_name: String,
    pub tool_version: String,
    pub run_id: String,
    pub created_utc: String,
    pub root: String,
    pub policy: ScanPolicy,
    pub items: Vec<ItemRecord>,
    pub summary: ScanSummary,
    pub manifest_sha256: String,
}
