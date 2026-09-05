use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use mcr_ingest::{
    model::{Manifest, ScanPolicy},
    report::{write_json_atomic, write_markdown_atomic},
    scanner::{scan, verify_manifest_hash},
};
use std::{fs::File, io::BufReader, path::PathBuf};

#[derive(Parser)]
#[command(
    name = "mcr-ingest",
    version,
    about = "Read-only evidence inventory and hostile-state detector"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    Scan {
        root: PathBuf,
        #[arg(long, short = 'o', default_value = "mcr-ingest-manifest.json")]
        output: PathBuf,
        #[arg(long)]
        report: Option<PathBuf>,
        #[arg(long, default_value_t=8 * 1024 * 1024 * 1024_u64)]
        max_file_bytes: u64,
        #[arg(long, default_value_t = 100_000)]
        max_archive_entries: usize,
        #[arg(long, default_value_t=64 * 1024 * 1024 * 1024_u64)]
        max_archive_uncompressed_bytes: u64,
        #[arg(long, default_value_t = 1_000.0)]
        max_archive_ratio: f64,
    },
    Verify {
        manifest: PathBuf,
    },
}

fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Command::Scan {
            root,
            output,
            report,
            max_file_bytes,
            max_archive_entries,
            max_archive_uncompressed_bytes,
            max_archive_ratio,
        } => {
            let policy = ScanPolicy {
                max_file_bytes,
                max_archive_entries,
                max_archive_total_uncompressed_bytes: max_archive_uncompressed_bytes,
                max_archive_entry_ratio: max_archive_ratio,
                ..Default::default()
            };
            let manifest = scan(&root, policy)?;
            write_json_atomic(&output, &manifest)?;
            if let Some(path) = report {
                write_markdown_atomic(&path, &manifest)?;
            }
            println!(
                "manifest={} sha256={} critical={} high={} errors={}",
                output.display(),
                manifest.manifest_sha256,
                manifest.summary.findings_critical,
                manifest.summary.findings_high,
                manifest.summary.errors
            );
            if manifest.summary.findings_critical > 0 {
                std::process::exit(3);
            }
            if manifest.summary.errors > 0 || manifest.summary.findings_high > 0 {
                std::process::exit(2);
            }
        }
        Command::Verify { manifest } => {
            let f = File::open(&manifest)
                .with_context(|| format!("open manifest: {}", manifest.display()))?;
            let parsed: Manifest =
                serde_json::from_reader(BufReader::new(f)).context("parse manifest JSON")?;
            if verify_manifest_hash(&parsed)? {
                println!("VALID {}", parsed.manifest_sha256);
            } else {
                eprintln!("INVALID manifest hash");
                std::process::exit(4);
            }
        }
    }
    Ok(())
}
