//! MBOX structural scanning.
//!
//! Donor lineage:
//! - adapted from dcarrero/mboxshell v0.7.3
//! - upstream commit 20a2b7842e91da1a21a71591e291333c50c5ebe5
//! - MIT License, Copyright (c) 2026 David Carrero Fernández-Baillo
//!
//! MCR hardening differences:
//! - output is a byte-span inventory, not a UI cache;
//! - complete MBOX SHA-256 is required separately;
//! - each raw message gets its own SHA-256 after indexing;
//! - Message-ID is metadata, never object identity;
//! - parser warnings never alter source bytes.

use std::io::{self, BufRead};

const MAX_LINE_RETAIN: usize = 8 * 1024 * 1024;
const MAX_HEADER_RETAIN: usize = 16 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MessageSpan {
    pub offset: u64,
    pub length: u64,
    pub header_bytes: Vec<u8>,
    pub separator_without_blank_line: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FromLineKind {
    Content,
    Separator,
    GitPatchMarker,
}

pub fn scan_headers<R: BufRead>(mut reader: R) -> io::Result<Vec<MessageSpan>> {
    let mut spans = Vec::new();
    let mut current_offset = 0u64;
    let mut first_line = true;
    let mut prev_line_was_empty = true;
    let mut git_patch_mbox = false;

    let mut current_start: Option<u64> = None;
    let mut current_warning = false;
    let mut in_headers = false;
    let mut header_buf = Vec::with_capacity(16 * 1024);
    let mut saved_headers: Option<Vec<u8>> = None;
    let mut line = Vec::with_capacity(4096);

    loop {
        line.clear();
        let consumed = reader.read_until(b'\n', &mut line)?;
        if consumed == 0 {
            break;
        }
        let line_len = consumed as u64;

        // Preserve exact offset accounting even if the retained copy is capped.
        if line.len() > MAX_LINE_RETAIN {
            line.truncate(MAX_LINE_RETAIN);
        }

        let kind = classify_from_line(&line);
        if first_line && kind == FromLineKind::GitPatchMarker {
            git_patch_mbox = true;
        }
        let is_separator = match kind {
            FromLineKind::Separator => true,
            FromLineKind::GitPatchMarker => git_patch_mbox,
            FromLineKind::Content => first_line && starts_with_from(&line),
        };

        if is_separator {
            if let Some(start) = current_start {
                let headers = saved_headers
                    .take()
                    .unwrap_or_else(|| std::mem::take(&mut header_buf));
                spans.push(MessageSpan {
                    offset: start,
                    length: current_offset - start,
                    header_bytes: headers,
                    separator_without_blank_line: current_warning,
                });
            }

            current_warning = !first_line && !prev_line_was_empty;
            header_buf.clear();
            header_buf.extend_from_slice(&line);
            saved_headers = None;
            in_headers = true;
            current_start = Some(current_offset);
        } else if in_headers {
            if is_blank_line(&line) {
                in_headers = false;
                saved_headers = Some(std::mem::take(&mut header_buf));
            } else if header_buf.len() < MAX_HEADER_RETAIN {
                let remaining = MAX_HEADER_RETAIN - header_buf.len();
                header_buf.extend_from_slice(&line[..line.len().min(remaining)]);
            }
        }

        prev_line_was_empty = is_blank_line(&line);
        first_line = false;
        current_offset += line_len;
    }

    if let Some(start) = current_start {
        spans.push(MessageSpan {
            offset: start,
            length: current_offset - start,
            header_bytes: saved_headers.unwrap_or(header_buf),
            separator_without_blank_line: current_warning,
        });
    }

    Ok(spans)
}

fn starts_with_from(line: &[u8]) -> bool {
    let line = line.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(line);
    line.starts_with(b"From ")
}

fn classify_from_line(line: &[u8]) -> FromLineKind {
    let line = line.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(line);
    if !line.starts_with(b"From ") {
        return FromLineKind::Content;
    }
    let Ok(rest) = std::str::from_utf8(&line[5..]) else {
        return FromLineKind::Content;
    };
    let tokens: Vec<&str> = rest.split_ascii_whitespace().collect();

    let date = match tokens.len() {
        0 => return FromLineKind::Separator,
        6 => &tokens[1..6],
        7 if is_timezone(tokens[6]) => &tokens[1..6],
        7 if is_timezone(tokens[5]) && is_year(tokens[6]) => &tokens[1..5],
        _ => return FromLineKind::Content,
    };

    let valid = match date {
        [dow, mon, day, time, year] => {
            is_day_of_week(dow) && is_month(mon) && is_day(day) && is_time(time) && is_year(year)
        }
        [dow, mon, day, time] => {
            is_day_of_week(dow) && is_month(mon) && is_day(day) && is_time(time)
        }
        _ => false,
    };
    if !valid {
        return FromLineKind::Content;
    }

    if rest.trim_end().ends_with("Mon Sep 17 00:00:00 2001") {
        FromLineKind::GitPatchMarker
    } else {
        FromLineKind::Separator
    }
}

fn is_day_of_week(s: &str) -> bool {
    matches!(s, "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat" | "Sun")
}

fn is_month(s: &str) -> bool {
    matches!(s, "Jan" | "Feb" | "Mar" | "Apr" | "May" | "Jun"
        | "Jul" | "Aug" | "Sep" | "Oct" | "Nov" | "Dec")
}

fn is_day(s: &str) -> bool {
    (1..=2).contains(&s.len()) && s.parse::<u8>().is_ok_and(|d| (1..=31).contains(&d))
}

fn is_time(s: &str) -> bool {
    let mut parts = s.split(':');
    let (Some(h), Some(m), Some(sec), None) =
        (parts.next(), parts.next(), parts.next(), parts.next())
    else {
        return false;
    };
    let ok = |t: &str, max: u8| {
        (1..=2).contains(&t.len()) && t.parse::<u8>().is_ok_and(|v| v <= max)
    };
    ok(h, 23) && ok(m, 59) && ok(sec, 61)
}

fn is_year(s: &str) -> bool {
    s.len() == 4 && s.bytes().all(|b| b.is_ascii_digit())
}

fn is_timezone(s: &str) -> bool {
    let numeric = (s.starts_with('+') || s.starts_with('-'))
        && s.len() == 5
        && s[1..].bytes().all(|b| b.is_ascii_digit());
    let named = (1..=5).contains(&s.len()) && s.bytes().all(|b| b.is_ascii_uppercase());
    numeric || named
}

fn is_blank_line(line: &[u8]) -> bool {
    line.iter().all(|&b| matches!(b, b'\n' | b'\r' | b' ' | b'\t'))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn indexes_two_messages_and_keeps_body_from_line_as_content() {
        let data = b"From a@example.com Thu Jan 01 00:00:00 2024\n\
Subject: one\n\n\
Body\n\
From this is quoted body text, not a valid separator\n\
\n\
From b@example.com Fri Jan 02 01:02:03 2024\n\
Subject: two\n\n\
End\n";
        let spans = scan_headers(Cursor::new(data)).unwrap();
        assert_eq!(spans.len(), 2);
        assert_eq!(spans[0].offset, 0);
        assert!(spans[0].length > 0);
        assert!(String::from_utf8_lossy(&spans[0].header_bytes).contains("Subject: one"));
        assert!(String::from_utf8_lossy(&spans[1].header_bytes).contains("Subject: two"));
    }

    #[test]
    fn accepts_thunderbird_bare_from_separator() {
        let data = b"From \nSubject: one\n\nBody\n\nFrom \nSubject: two\n\nBody\n";
        let spans = scan_headers(Cursor::new(data)).unwrap();
        assert_eq!(spans.len(), 2);
    }

    #[test]
    fn does_not_split_git_patch_marker_inside_normal_mailbox() {
        let data = b"From a@example.com Thu Jan 01 00:00:00 2024\n\
Subject: one\n\n\
From nobody Mon Sep 17 00:00:00 2001\n\
patch body\n";
        let spans = scan_headers(Cursor::new(data)).unwrap();
        assert_eq!(spans.len(), 1);
    }
}
