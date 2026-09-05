//! Evidence-aware mail threading.
//!
//! Donor lineage:
//! - adapted from dcarrero/mboxshell v0.7.3 `src/tui/threading.rs`
//! - upstream commit 20a2b7842e91da1a21a71591e291333c50c5ebe5
//! - MIT License, Copyright (c) 2026 David Carrero Fernández-Baillo
//!
//! MCR hardening differences:
//! - subject-only grouping is labelled HEURISTIC, never factual linkage;
//! - `X-GM-THRID`/platform thread ids are kept separate from RFC header links;
//! - duplicate Message-ID values never collapse byte occurrences;
//! - references to duplicated Message-ID values stay occurrence-ambiguous;
//! - missing Message-ID values get internal-only keys, never invented RFC ids;
//! - conflicts between explicit platform ids are surfaced, not silently resolved;
//! - cycle prevention uses visited-container detection rather than a guessed depth ceiling.

use std::collections::{HashMap, HashSet};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ThreadMessage {
    pub message_id: Option<String>,
    pub in_reply_to: Option<String>,
    pub references: Vec<String>,
    pub subject: String,
    pub platform_thread_id: Option<String>,
    /// Caller-provided chronological sort key. This module does not infer time zones.
    pub sort_key: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GroupBasis {
    Singleton,
    RfcHeaderStructure,
    ExplicitPlatformThreadId,
    SubjectHeuristic,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeclaredLinkKind {
    References,
    InReplyTo,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeclaredLink {
    pub source_index: usize,
    pub target_message_id: String,
    /// Resolved only when exactly one occurrence claims this Message-ID.
    pub target_index: Option<usize>,
    pub target_ambiguous: bool,
    pub kind: DeclaredLinkKind,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DuplicateMessageId {
    pub normalized_message_id: String,
    pub occurrence_indices: Vec<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ThreadGroup {
    pub members: Vec<usize>,
    pub basis: GroupBasis,
    pub normalized_subject: String,
    pub platform_thread_id: Option<String>,
    pub platform_thread_id_conflict: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ThreadAnalysis {
    pub groups: Vec<ThreadGroup>,
    pub declared_links: Vec<DeclaredLink>,
    pub duplicate_message_ids: Vec<DuplicateMessageId>,
    pub missing_message_id_indices: Vec<usize>,
}

#[derive(Debug, Clone)]
struct Container {
    entry_index: Option<usize>,
    parent: Option<String>,
    children: Vec<String>,
}

pub fn analyse_threads(entries: &[ThreadMessage]) -> ThreadAnalysis {
    let normalized_ids: Vec<Option<String>> = entries
        .iter()
        .map(|entry| {
            entry
                .message_id
                .as_deref()
                .map(normalize_id)
                .filter(|s| !s.is_empty())
        })
        .collect();

    let mut occurrences_by_id: HashMap<String, Vec<usize>> = HashMap::new();
    let mut missing_message_id_indices = Vec::new();
    for (idx, normalized) in normalized_ids.iter().enumerate() {
        if let Some(mid) = normalized {
            occurrences_by_id.entry(mid.clone()).or_default().push(idx);
        } else {
            missing_message_id_indices.push(idx);
        }
    }

    let mut duplicate_message_ids: Vec<DuplicateMessageId> = occurrences_by_id
        .iter()
        .filter(|(_, indices)| indices.len() > 1)
        .map(|(mid, indices)| DuplicateMessageId {
            normalized_message_id: mid.clone(),
            occurrence_indices: indices.clone(),
        })
        .collect();
    duplicate_message_ids.sort_by(|a, b| a.normalized_message_id.cmp(&b.normalized_message_id));

    let unique_target_index: HashMap<String, usize> = occurrences_by_id
        .iter()
        .filter_map(|(mid, indices)| (indices.len() == 1).then_some((mid.clone(), indices[0])))
        .collect();
    let duplicate_ids: HashSet<String> = duplicate_message_ids
        .iter()
        .map(|d| d.normalized_message_id.clone())
        .collect();

    let mut containers: HashMap<String, Container> = HashMap::new();
    let mut entry_keys = Vec::with_capacity(entries.len());

    for (idx, normalized) in normalized_ids.iter().enumerate() {
        let key = match normalized {
            None => internal_missing_key(idx),
            Some(mid) if duplicate_ids.contains(mid) => internal_duplicate_occurrence_key(idx),
            Some(mid) => mid.clone(),
        };
        containers.insert(
            key.clone(),
            Container {
                entry_index: Some(idx),
                parent: None,
                children: Vec::new(),
            },
        );
        entry_keys.push(key);
    }

    // Duplicate identifiers get a neutral placeholder. References to the
    // duplicated Message-ID may attach beneath this placeholder, but no actual
    // duplicate occurrence is silently selected as the target.
    for mid in &duplicate_ids {
        containers.entry(mid.clone()).or_insert_with(|| Container {
            entry_index: None,
            parent: None,
            children: Vec::new(),
        });
    }

    let mut declared_links = Vec::new();
    for (idx, entry) in entries.iter().enumerate() {
        for rid in entry
            .references
            .iter()
            .map(|r| normalize_id(r))
            .filter(|r| !r.is_empty())
        {
            declared_links.push(DeclaredLink {
                source_index: idx,
                target_index: unique_target_index.get(&rid).copied(),
                target_ambiguous: duplicate_ids.contains(&rid),
                target_message_id: rid,
                kind: DeclaredLinkKind::References,
            });
        }

        if let Some(reply) = entry
            .in_reply_to
            .as_deref()
            .map(normalize_id)
            .filter(|r| !r.is_empty())
        {
            declared_links.push(DeclaredLink {
                source_index: idx,
                target_index: unique_target_index.get(&reply).copied(),
                target_ambiguous: duplicate_ids.contains(&reply),
                target_message_id: reply,
                kind: DeclaredLinkKind::InReplyTo,
            });
        }
    }

    // Construct a JWZ-style internal container graph. It is a processing
    // structure only; declared_links above is the evidential record of what
    // headers actually stated.
    for (idx, entry) in entries.iter().enumerate() {
        let current_key = entry_keys[idx].clone();
        let mut refs: Vec<String> = entry
            .references
            .iter()
            .map(|r| normalize_id(r))
            .filter(|r| !r.is_empty())
            .collect();

        if let Some(reply) = entry
            .in_reply_to
            .as_deref()
            .map(normalize_id)
            .filter(|r| !r.is_empty())
        {
            if !refs.contains(&reply) {
                refs.push(reply);
            }
        }

        for rid in &refs {
            containers.entry(rid.clone()).or_insert_with(|| Container {
                entry_index: None,
                parent: None,
                children: Vec::new(),
            });
        }

        let mut chain = refs;
        chain.push(current_key);

        for pair in chain.windows(2) {
            let parent_id = &pair[0];
            let child_id = &pair[1];

            if parent_id == child_id || would_create_cycle(&containers, parent_id, child_id) {
                continue;
            }

            if let Some(old_parent_id) = containers.get(child_id).and_then(|c| c.parent.clone()) {
                if old_parent_id != *parent_id {
                    if let Some(old_parent) = containers.get_mut(&old_parent_id) {
                        old_parent.children.retain(|c| c != child_id);
                    }
                }
            }

            if let Some(child) = containers.get_mut(child_id) {
                child.parent = Some(parent_id.clone());
            }
            if let Some(parent) = containers.get_mut(parent_id) {
                if !parent.children.contains(child_id) {
                    parent.children.push(child_id.clone());
                }
            }
        }
    }

    let root_ids: Vec<String> = containers
        .iter()
        .filter_map(|(id, c)| c.parent.is_none().then_some(id.clone()))
        .collect();

    // Exact platform ids can merge otherwise-disconnected roots. Subject-only
    // grouping remains available solely as an explicit heuristic bucket.
    let mut root_buckets: HashMap<String, Vec<String>> = HashMap::new();
    for root_id in &root_ids {
        let subtree_ids = subtree_platform_thread_ids(root_id, &containers, entries);
        let key = if subtree_ids.len() == 1 {
            format!("platform\0{}", subtree_ids[0])
        } else {
            let subject = first_subject(root_id, &containers, entries);
            if subject.is_empty() {
                format!("root\0{root_id}")
            } else {
                format!("subject\0{subject}")
            }
        };
        root_buckets.entry(key).or_default().push(root_id.clone());
    }

    let mut groups = Vec::new();
    for (bucket_key, roots) in root_buckets {
        let mut members = Vec::new();
        for root in &roots {
            flatten_members(root, &containers, entries, &mut members);
        }

        members.sort_by_key(|&idx| (entries[idx].sort_key, idx));
        members.dedup();
        if members.is_empty() {
            continue;
        }

        let mut platform_ids: Vec<String> = members
            .iter()
            .filter_map(|&i| entries[i].platform_thread_id.clone())
            .filter(|s| !s.trim().is_empty())
            .collect();
        platform_ids.sort();
        platform_ids.dedup();

        let platform_thread_id_conflict = platform_ids.len() > 1;
        let platform_thread_id = (platform_ids.len() == 1).then(|| platform_ids[0].clone());

        let normalized_subject = members
            .iter()
            .map(|&i| normalize_subject(&entries[i].subject))
            .find(|s| !s.is_empty())
            .unwrap_or_default();

        let basis = if members.len() == 1 {
            GroupBasis::Singleton
        } else if bucket_key.starts_with("platform\0") {
            GroupBasis::ExplicitPlatformThreadId
        } else if roots.len() > 1 && bucket_key.starts_with("subject\0") {
            GroupBasis::SubjectHeuristic
        } else {
            GroupBasis::RfcHeaderStructure
        };

        groups.push(ThreadGroup {
            members,
            basis,
            normalized_subject,
            platform_thread_id,
            platform_thread_id_conflict,
        });
    }

    groups.sort_by_key(|group| {
        group
            .members
            .iter()
            .map(|&idx| entries[idx].sort_key)
            .max()
            .map(std::cmp::Reverse)
    });

    ThreadAnalysis {
        groups,
        declared_links,
        duplicate_message_ids,
        missing_message_id_indices,
    }
}

fn would_create_cycle(
    containers: &HashMap<String, Container>,
    parent_id: &str,
    child_id: &str,
) -> bool {
    let mut current = Some(parent_id.to_string());
    let mut visited = HashSet::new();

    while let Some(id) = current {
        if id == child_id || !visited.insert(id.clone()) {
            return true;
        }
        current = containers.get(&id).and_then(|c| c.parent.clone());
    }

    false
}

fn flatten_members(
    id: &str,
    containers: &HashMap<String, Container>,
    entries: &[ThreadMessage],
    out: &mut Vec<usize>,
) {
    let Some(container) = containers.get(id) else {
        return;
    };

    if let Some(idx) = container.entry_index {
        out.push(idx);
    }

    let mut children = container.children.clone();
    children.sort_by_key(|child| {
        containers
            .get(child)
            .and_then(|c| c.entry_index)
            .map(|idx| (entries[idx].sort_key, idx))
    });

    for child in children {
        flatten_members(&child, containers, entries, out);
    }
}

fn subtree_platform_thread_ids(
    root_id: &str,
    containers: &HashMap<String, Container>,
    entries: &[ThreadMessage],
) -> Vec<String> {
    let mut stack = vec![root_id.to_string()];
    let mut visited = HashSet::new();
    let mut ids = Vec::new();

    while let Some(id) = stack.pop() {
        if !visited.insert(id.clone()) {
            continue;
        }
        let Some(container) = containers.get(&id) else {
            continue;
        };

        if let Some(idx) = container.entry_index {
            if let Some(tid) = entries[idx]
                .platform_thread_id
                .as_ref()
                .filter(|s| !s.trim().is_empty())
            {
                ids.push(tid.clone());
            }
        }

        for child in &container.children {
            stack.push(child.clone());
        }
    }

    ids.sort();
    ids.dedup();
    ids
}

fn first_subject(
    root_id: &str,
    containers: &HashMap<String, Container>,
    entries: &[ThreadMessage],
) -> String {
    first_entry_index(root_id, containers)
        .map(|idx| normalize_subject(&entries[idx].subject))
        .unwrap_or_default()
}

fn first_entry_index(root_id: &str, containers: &HashMap<String, Container>) -> Option<usize> {
    let mut stack = vec![root_id.to_string()];
    let mut visited = HashSet::new();

    while let Some(id) = stack.pop() {
        if !visited.insert(id.clone()) {
            continue;
        }
        let container = containers.get(&id)?;
        if let Some(idx) = container.entry_index {
            return Some(idx);
        }
        for child in container.children.iter().rev() {
            stack.push(child.clone());
        }
    }

    None
}

fn internal_missing_key(index: usize) -> String {
    format!("\0mcr-missing-id\0{index}")
}

fn internal_duplicate_occurrence_key(index: usize) -> String {
    format!("\0mcr-duplicate-id-occurrence\0{index}")
}

pub fn normalize_id(id: &str) -> String {
    id.trim()
        .trim_start_matches('<')
        .trim_end_matches('>')
        .trim()
        .to_string()
}

pub fn normalize_subject(subject: &str) -> String {
    let mut s = subject.trim();

    loop {
        let stripped = if s.get(..3).is_some_and(|p| p.eq_ignore_ascii_case("re:")) {
            &s[3..]
        } else if s.get(..4).is_some_and(|p| p.eq_ignore_ascii_case("fwd:")) {
            &s[4..]
        } else if s.get(..3).is_some_and(|p| p.eq_ignore_ascii_case("fw:")) {
            &s[3..]
        } else {
            break;
        };
        s = stripped.trim_start();
    }

    s.to_lowercase()
}
