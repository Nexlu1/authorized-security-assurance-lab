use mcr_ingest::threading::{
    analyse_threads, DeclaredLinkKind, GroupBasis, ThreadMessage,
};

fn msg(
    message_id: Option<&str>,
    in_reply_to: Option<&str>,
    references: &[&str],
    subject: &str,
    platform_thread_id: Option<&str>,
    sort_key: i64,
) -> ThreadMessage {
    ThreadMessage {
        message_id: message_id.map(str::to_string),
        in_reply_to: in_reply_to.map(str::to_string),
        references: references.iter().map(|s| (*s).to_string()).collect(),
        subject: subject.to_string(),
        platform_thread_id: platform_thread_id.map(str::to_string),
        sort_key,
    }
}

#[test]
fn rfc_reply_chain_is_explicit_structure_not_subject_heuristic() {
    let entries = vec![
        msg(Some("<a@example>"), None, &[], "Topic", None, 1),
        msg(
            Some("<b@example>"),
            Some("<a@example>"),
            &["<a@example>"],
            "Re: Topic",
            None,
            2,
        ),
    ];
    let result = analyse_threads(&entries);
    assert_eq!(result.groups.len(), 1);
    assert_eq!(result.groups[0].members, vec![0, 1]);
    assert_eq!(result.groups[0].basis, GroupBasis::RfcHeaderStructure);
    assert!(result.declared_links.iter().any(|link| {
        link.source_index == 1
            && link.target_index == Some(0)
            && !link.target_ambiguous
            && link.kind == DeclaredLinkKind::InReplyTo
    }));
}

#[test]
fn subject_only_merge_is_labelled_heuristic() {
    let entries = vec![
        msg(Some("<a@example>"), None, &[], "Meeting", None, 1),
        msg(Some("<b@example>"), None, &[], "Re: Meeting", None, 2),
    ];
    let result = analyse_threads(&entries);
    assert_eq!(result.groups.len(), 1);
    assert_eq!(result.groups[0].basis, GroupBasis::SubjectHeuristic);
    assert!(result.declared_links.is_empty());
}

#[test]
fn exact_platform_ids_separate_same_subject_conversations() {
    let entries = vec![
        msg(Some("<a@example>"), None, &[], "Hello", Some("111"), 1),
        msg(Some("<b@example>"), None, &[], "Hello", Some("222"), 2),
    ];
    let result = analyse_threads(&entries);
    assert_eq!(result.groups.len(), 2);
    assert!(result.groups.iter().all(|g| g.basis == GroupBasis::Singleton));
}

#[test]
fn exact_platform_id_can_group_different_subject_roots() {
    let entries = vec![
        msg(Some("<a@example>"), None, &[], "Original", Some("111"), 1),
        msg(Some("<b@example>"), None, &[], "Edited subject", Some("111"), 2),
    ];
    let result = analyse_threads(&entries);
    assert_eq!(result.groups.len(), 1);
    assert_eq!(result.groups[0].members, vec![0, 1]);
    assert_eq!(
        result.groups[0].basis,
        GroupBasis::ExplicitPlatformThreadId
    );
    assert_eq!(result.groups[0].platform_thread_id.as_deref(), Some("111"));
}

#[test]
fn duplicate_message_id_reference_remains_occurrence_ambiguous() {
    let entries = vec![
        msg(Some("<dup@example>"), None, &[], "Copy A", None, 1),
        msg(Some("<dup@example>"), None, &[], "Copy B", None, 2),
        msg(
            Some("<reply@example>"),
            Some("<dup@example>"),
            &[],
            "Reply",
            None,
            3,
        ),
    ];
    let result = analyse_threads(&entries);
    assert_eq!(result.duplicate_message_ids.len(), 1);
    assert_eq!(
        result.duplicate_message_ids[0].occurrence_indices,
        vec![0, 1]
    );
    let link = result
        .declared_links
        .iter()
        .find(|link| link.source_index == 2 && link.kind == DeclaredLinkKind::InReplyTo)
        .expect("in-reply-to evidence");
    assert_eq!(link.target_index, None);
    assert!(link.target_ambiguous);
    assert_eq!(result.groups.len(), 3);
}

#[test]
fn missing_message_id_is_recorded_without_inventing_an_rfc_id() {
    let entries = vec![msg(None, None, &[], "No id", None, 1)];
    let result = analyse_threads(&entries);
    assert_eq!(result.missing_message_id_indices, vec![0]);
    assert_eq!(result.groups.len(), 1);
    assert_eq!(result.groups[0].basis, GroupBasis::Singleton);
}

#[test]
fn conflicting_platform_ids_inside_rfc_chain_are_surfaced() {
    let entries = vec![
        msg(Some("<a@example>"), None, &[], "Topic", Some("111"), 1),
        msg(
            Some("<b@example>"),
            Some("<a@example>"),
            &["<a@example>"],
            "Re: Topic",
            Some("222"),
            2,
        ),
    ];
    let result = analyse_threads(&entries);
    assert_eq!(result.groups.len(), 1);
    assert_eq!(result.groups[0].basis, GroupBasis::RfcHeaderStructure);
    assert!(result.groups[0].platform_thread_id_conflict);
    assert_eq!(result.groups[0].platform_thread_id, None);
}

#[test]
fn cyclic_reference_headers_do_not_create_recursive_loop() {
    let entries = vec![
        msg(Some("<a@example>"), None, &["<b@example>"], "Cycle", None, 1),
        msg(Some("<b@example>"), None, &["<a@example>"], "Cycle", None, 2),
    ];
    let result = analyse_threads(&entries);
    let shown: Vec<usize> = result
        .groups
        .iter()
        .flat_map(|g| g.members.iter().copied())
        .collect();
    assert_eq!(shown.len(), 2);
    assert!(shown.contains(&0));
    assert!(shown.contains(&1));
}
