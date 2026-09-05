use mcr_ingest::mbox_scan::scan_headers;
use std::io::Cursor;

#[test]
fn embedded_git_patch_text_does_not_split_normal_mailbox() {
    let data = b"From a@example.com Thu Jan 01 00:00:00 2024\nSubject: Patch review\n\nThanks,<br>\n<br>\nFrom abc123 Mon Sep 17 00:00:00 2001<br>\nFrom: quoted@example.com<br>\n\nFrom abc123 Mon Sep 17 00:00:00 2001\nFrom: quoted@example.com\n\nFrom b@example.com Thu Jan 02 00:00:00 2024\nSubject: Second real message\n\nBody\n";
    let spans = scan_headers(Cursor::new(data)).unwrap();
    assert_eq!(spans.len(), 2);
}

#[test]
fn genuine_git_patch_series_still_splits() {
    let mut data = Vec::new();
    for i in 1..=3 {
        data.extend_from_slice(b"From 8f3b1c4d5e6f Mon Sep 17 00:00:00 2001\n");
        data.extend_from_slice(format!("Subject: [PATCH {i}/3] change\n\n").as_bytes());
        data.extend_from_slice(b"diff --git a/x b/x\n\n");
    }
    let spans = scan_headers(Cursor::new(data)).unwrap();
    assert_eq!(spans.len(), 3);
}

#[test]
fn utf8_bom_before_first_separator_is_tolerated_without_offset_rewrite() {
    let mut data = vec![0xEF, 0xBB, 0xBF];
    data.extend_from_slice(b"From a@example.com Thu Jan 01 00:00:00 2024\nSubject: one\n\nBody\n");
    let spans = scan_headers(Cursor::new(&data)).unwrap();
    assert_eq!(spans.len(), 1);
    assert_eq!(spans[0].offset, 0);
    assert_eq!(spans[0].length, data.len() as u64);
}

#[test]
fn oversized_physical_line_keeps_later_offset_exact() {
    const RETAIN_LIMIT: usize = 8 * 1024 * 1024;
    let mut data = Vec::new();
    data.extend_from_slice(b"From a@example.com Thu Jan 01 00:00:00 2024\nSubject: First\n\n");
    data.extend(std::iter::repeat_n(b'x', RETAIN_LIMIT + 1024));
    data.push(b'\n');
    let second_start = data.len() as u64;
    data.extend_from_slice(
        b"From b@example.com Fri Jan 02 00:00:00 2024\nSubject: Second\n\nBody\n",
    );

    let spans = scan_headers(Cursor::new(&data)).unwrap();
    assert_eq!(spans.len(), 2);
    assert_eq!(spans[1].offset, second_start);
    assert_eq!(spans[1].offset + spans[1].length, data.len() as u64);
}

#[test]
fn intermediate_message_without_blank_line_is_not_dropped() {
    let data = b"From a@example.com Thu Jan 01 00:00:00 2024\nSubject: First\nFrom b@example.com Fri Jan 02 00:00:00 2024\nSubject: Second\n\nBody\n";
    let spans = scan_headers(Cursor::new(data)).unwrap();
    assert_eq!(spans.len(), 2);
    assert!(String::from_utf8_lossy(&spans[0].header_bytes).contains("Subject: First"));
    assert!(String::from_utf8_lossy(&spans[1].header_bytes).contains("Subject: Second"));
    assert!(spans[1].separator_without_blank_line);
}
