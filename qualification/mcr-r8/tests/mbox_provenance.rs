use mcr_ingest::mbox_scan::scan_headers;
use std::io::Cursor;

#[test]
fn synthetic_mbox_offsets_are_monotonic_and_bounded() {
    let data = b"From a@example.com Thu Jan 01 00:00:00 2024\nSubject: one\n\nA\n\n\
From b@example.com Fri Jan 02 00:00:00 2024\nSubject: two\n\nB\n";
    let spans = scan_headers(Cursor::new(data)).unwrap();
    assert_eq!(spans.len(), 2);
    assert_eq!(spans[0].offset, 0);
    assert!(spans[0].offset + spans[0].length <= data.len() as u64);
    assert!(spans[1].offset > spans[0].offset);
    assert_eq!(spans[1].offset + spans[1].length, data.len() as u64);
}

#[test]
fn malformed_separator_is_recorded_not_silently_normalised() {
    let data = b"From a@example.com Thu Jan 01 00:00:00 2024\nSubject: one\n\nBody without blank before next separator\nFrom b@example.com Fri Jan 02 00:00:00 2024\nSubject: two\n\nB\n";
    let spans = scan_headers(Cursor::new(data)).unwrap();
    assert_eq!(spans.len(), 2);
    assert!(spans[1].separator_without_blank_line);
}
