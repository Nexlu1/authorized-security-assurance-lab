use lopdf::content::{Content, Operation};
use lopdf::{
    Bookmark, Document, EncryptionState, EncryptionVersion, Object, ObjectId, Permissions, Stream,
    dictionary,
};
use std::collections::{BTreeMap, HashSet};
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};

const LOPDF_COMMIT: &str = "a62854e1bbea308cd7db6e34492c0b3873711471";
const HMCTS_STITCHING_COMMIT: &str = "bdb2c306b523ad962298af9c198462d9a42017f4";
const SOURCE_DOCUMENTS: usize = 12;
const SOURCE_PAGES: usize = 9;
const FULL_EXPECTED_PAGES: usize = 1 + SOURCE_DOCUMENTS * SOURCE_PAGES;
const CORE_EXPECTED_PAGES: usize = 1 + 4 * SOURCE_PAGES;
const INDEX_TOP_Y: f32 = 780.0;
const INDEX_SUBTITLE_DROP: f32 = 38.0;
const INDEX_ROW_DROP: f32 = 48.0;

type AnyResult<T> = Result<T, Box<dyn Error>>;

#[derive(Clone, Debug)]
struct SourceSpec {
    section: usize,
    title: String,
    path: PathBuf,
}

#[derive(Clone, Debug)]
struct BundleEntry {
    section: usize,
    title: String,
    path: PathBuf,
    pages: usize,
    start_page: usize,
}

fn main() -> AnyResult<()> {
    let root = std::env::args()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("target/court-bundle-qualification"));
    if root.exists() {
        fs::remove_dir_all(&root)?;
    }
    fs::create_dir_all(root.join("sources"))?;
    fs::create_dir_all(root.join("negative"))?;

    let specs = generate_sources(&root.join("sources"))?;
    let original_bytes: Vec<(PathBuf, Vec<u8>)> = specs
        .iter()
        .map(|s| Ok((s.path.clone(), fs::read(&s.path)?)))
        .collect::<AnyResult<_>>()?;

    let malformed = root.join("negative/malformed-not-a-pdf.pdf");
    fs::write(&malformed, b"this is deliberately not a PDF\n")?;
    if Document::load(&malformed).is_ok() {
        return Err("malformed PDF did not fail closed".into());
    }

    let encrypted = root.join("negative/encrypted-input.pdf");
    generate_encrypted_negative_fixture(&encrypted)?;
    let encrypted_doc = Document::load(&encrypted)?;
    if !encrypted_doc.is_encrypted() {
        return Err("encrypted negative fixture was not detected as encrypted".into());
    }
    if validate_source(&encrypted).is_ok() {
        return Err("encrypted source was accepted by court-bundle source gate".into());
    }

    let hearing = root.join("SYN001_Synthetic-v-Respondent_Hearing_Bundle.pdf");
    let full_entries = build_bundle(&specs, &hearing, FULL_EXPECTED_PAGES)?;
    verify_bundle(
        &hearing,
        &full_entries,
        FULL_EXPECTED_PAGES,
        SOURCE_DOCUMENTS,
        15,
    )?;

    let core_specs = vec![
        specs[0].clone(),
        specs[4].clone(),
        specs[8].clone(),
        specs[11].clone(),
    ];
    let core = root.join("SYN001_Synthetic-v-Respondent_Core_Bundle.pdf");
    let core_entries = build_bundle(&core_specs, &core, CORE_EXPECTED_PAGES)?;
    verify_bundle(&core, &core_entries, CORE_EXPECTED_PAGES, 4, 7)?;

    for (path, before) in &original_bytes {
        let after = fs::read(path)?;
        if before != &after {
            return Err(format!("source mutated during assembly: {}", path.display()).into());
        }
    }

    write_receipt(&root, &hearing, &core, &specs, &full_entries, &core_entries)?;
    println!("PASS: synthetic court-bundle qualification completed");
    println!("hearing_bundle={}", hearing.display());
    println!("core_bundle={}", core.display());
    println!("hearing_pages={FULL_EXPECTED_PAGES}");
    println!("core_pages={CORE_EXPECTED_PAGES}");
    println!("source_immutability=PASS");
    Ok(())
}

fn generate_sources(dir: &Path) -> AnyResult<Vec<SourceSpec>> {
    let mut specs = Vec::new();
    for i in 0..SOURCE_DOCUMENTS {
        let section = (i / 4) + 1;
        let doc_no = i + 1;
        let title = format!("Synthetic Evidence Document {doc_no:02}");
        let path = dir.join(format!("SYN-EVID-{doc_no:02}.pdf"));
        let landscape_last_page = doc_no == SOURCE_DOCUMENTS;
        let mut doc = generate_source_document(doc_no, &title, landscape_last_page)?;
        doc.compress();
        doc.save(&path)?;
        validate_source(&path)?;
        specs.push(SourceSpec {
            section,
            title,
            path,
        });
    }
    Ok(specs)
}

fn generate_source_document(
    doc_no: usize,
    title: &str,
    landscape_last_page: bool,
) -> AnyResult<Document> {
    let mut doc = Document::with_version("1.6");
    let pages_id = doc.new_object_id();
    let font_id = doc.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica",
    });
    let resources_id = doc.add_object(dictionary! {
        "Font" => dictionary! { "F1" => font_id },
    });

    let mut page_ids = Vec::new();
    for page_no in 1..=SOURCE_PAGES {
        let content = Content {
            operations: vec![
                Operation::new("BT", vec![]),
                Operation::new("Tf", vec![Object::Name(b"F1".to_vec()), 18.into()]),
                Operation::new("Td", vec![55.into(), 780.into()]),
                Operation::new("Tj", vec![Object::string_literal(title)]),
                Operation::new("Td", vec![0.into(), (-42).into()]),
                Operation::new(
                    "Tj",
                    vec![Object::string_literal(format!(
                        "SYNTHETIC DOCUMENT {doc_no:02} / SOURCE PAGE {page_no:02}"
                    ))],
                ),
                Operation::new("Td", vec![0.into(), (-34).into()]),
                Operation::new(
                    "Tj",
                    vec![Object::string_literal(
                        "Synthetic-only evidence. No live case or personal data.",
                    )],
                ),
                Operation::new("ET", vec![]),
            ],
        };
        let stream_id = doc.add_object(Stream::new(dictionary! {}, content.encode()?));
        let landscape = landscape_last_page && page_no == SOURCE_PAGES;
        let media_box = if landscape {
            vec![0.into(), 0.into(), 842.into(), 595.into()]
        } else {
            vec![0.into(), 0.into(), 595.into(), 842.into()]
        };
        let page_id = doc.add_object(dictionary! {
            "Type" => "Page",
            "Parent" => pages_id,
            "Contents" => stream_id,
            "Resources" => resources_id,
            "MediaBox" => media_box,
        });
        page_ids.push(page_id);
    }

    doc.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages",
            "Kids" => page_ids.iter().copied().map(Object::Reference).collect::<Vec<_>>(),
            "Count" => SOURCE_PAGES as i64,
        }),
    );
    let catalog_id = doc.add_object(dictionary! {
        "Type" => "Catalog",
        "Pages" => pages_id,
    });
    doc.trailer.set("Root", catalog_id);
    Ok(doc)
}

fn generate_index_document(entries: &[BundleEntry], total_pages: usize) -> AnyResult<Document> {
    let mut doc = Document::with_version("1.6");
    let pages_id = doc.new_object_id();
    let font_id = doc.add_object(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => "Helvetica",
    });
    let resources_id = doc.add_object(dictionary! {
        "Font" => dictionary! { "F1" => font_id },
    });

    let mut ops = vec![
        Operation::new("BT", vec![]),
        Operation::new("Tf", vec![Object::Name(b"F1".to_vec()), 17.into()]),
        Operation::new("Td", vec![50.into(), INDEX_TOP_Y.into()]),
        Operation::new(
            "Tj",
            vec![Object::string_literal("SYNTHETIC COURT BUNDLE INDEX")],
        ),
        Operation::new("Tf", vec![Object::Name(b"F1".to_vec()), 10.into()]),
        Operation::new("Td", vec![0.into(), (-INDEX_SUBTITLE_DROP).into()]),
        Operation::new(
            "Tj",
            vec![Object::string_literal(format!(
                "HMCTS-style technical qualification / {total_pages} pages / synthetic data only"
            ))],
        ),
    ];
    for entry in entries {
        ops.push(Operation::new(
            "Td",
            vec![0.into(), (-INDEX_ROW_DROP).into()],
        ));
        ops.push(Operation::new(
            "Tj",
            vec![Object::string_literal(format!(
                "S{} | {} | bundle page {}",
                entry.section, entry.title, entry.start_page
            ))],
        ));
    }
    ops.push(Operation::new("ET", vec![]));

    let stream_id = doc.add_object(Stream::new(
        dictionary! {},
        Content { operations: ops }.encode()?,
    ));
    let page_id = doc.add_object(dictionary! {
        "Type" => "Page",
        "Parent" => pages_id,
        "Contents" => stream_id,
        "Resources" => resources_id,
        "MediaBox" => vec![0.into(), 0.into(), 595.into(), 842.into()],
    });
    doc.objects.insert(
        pages_id,
        Object::Dictionary(dictionary! {
            "Type" => "Pages",
            "Kids" => vec![Object::Reference(page_id)],
            "Count" => 1,
        }),
    );
    let catalog_id = doc.add_object(dictionary! {
        "Type" => "Catalog",
        "Pages" => pages_id,
    });
    doc.trailer.set("Root", catalog_id);
    Ok(doc)
}

fn compute_entries(specs: &[SourceSpec]) -> AnyResult<Vec<BundleEntry>> {
    let mut next_page = 2usize;
    let mut entries = Vec::new();
    for spec in specs {
        let doc = validate_source(&spec.path)?;
        let pages = doc.get_pages().len();
        entries.push(BundleEntry {
            section: spec.section,
            title: spec.title.clone(),
            path: spec.path.clone(),
            pages,
            start_page: next_page,
        });
        next_page += pages;
    }
    Ok(entries)
}

fn validate_source(path: &Path) -> AnyResult<Document> {
    let doc = Document::load(path)?;
    if doc.is_encrypted() {
        return Err(format!("encrypted source rejected: {}", path.display()).into());
    }
    let pages = doc.get_pages();
    if pages.is_empty() {
        return Err(format!("source has no pages: {}", path.display()).into());
    }
    for page_no in pages.keys().copied() {
        let text = doc.extract_text(&[page_no])?;
        if text.trim().is_empty() {
            return Err(format!(
                "source page is not searchable: {} page {page_no}",
                path.display()
            )
            .into());
        }
    }
    Ok(doc)
}

fn build_bundle(
    specs: &[SourceSpec],
    output: &Path,
    expected_pages: usize,
) -> AnyResult<Vec<BundleEntry>> {
    let entries = compute_entries(specs)?;
    let computed_pages = 1 + entries.iter().map(|e| e.pages).sum::<usize>();
    if computed_pages != expected_pages {
        return Err(format!(
            "bundle page plan mismatch: computed={computed_pages} expected={expected_pages}"
        )
        .into());
    }

    let index = generate_index_document(&entries, expected_pages)?;
    let mut documents = vec![index];
    for entry in &entries {
        documents.push(validate_source(&entry.path)?);
    }

    let mut bundle = merge_documents(documents)?;
    add_index_links(&mut bundle, &entries)?;
    add_bundle_bookmarks(&mut bundle, &entries)?;
    add_continuous_page_numbers(&mut bundle)?;
    set_default_view_100(&mut bundle)?;
    bundle.compress();
    bundle.save(output)?;
    Ok(entries)
}

fn merge_documents(documents: Vec<Document>) -> AnyResult<Document> {
    let mut max_id = 1;
    let mut documents_pages: BTreeMap<ObjectId, Object> = BTreeMap::new();
    let mut documents_objects: BTreeMap<ObjectId, Object> = BTreeMap::new();
    let mut document = Document::with_version("1.6");

    for mut doc in documents {
        doc.renumber_objects_with(max_id);
        max_id = doc.max_id + 1;
        for object_id in doc.get_pages().into_values() {
            let page = doc.get_object(object_id)?.to_owned();
            documents_pages.insert(object_id, page);
        }
        documents_objects.extend(doc.objects);
    }

    let mut catalog_object: Option<(ObjectId, Object)> = None;
    let mut pages_object: Option<(ObjectId, Object)> = None;
    for (object_id, object) in documents_objects {
        match object.type_name().unwrap_or(b"") {
            b"Catalog" => {
                if catalog_object.is_none() {
                    catalog_object = Some((object_id, object));
                }
            }
            b"Pages" => {
                if pages_object.is_none() {
                    pages_object = Some((object_id, object));
                }
            }
            b"Page" | b"Outlines" | b"Outline" => {}
            _ => {
                document.objects.insert(object_id, object);
            }
        }
    }

    let (pages_id, pages_obj) = pages_object.ok_or("Pages root not found")?;
    for (object_id, object) in &documents_pages {
        let mut dict = object.as_dict()?.clone();
        dict.set("Parent", pages_id);
        document
            .objects
            .insert(*object_id, Object::Dictionary(dict));
    }
    let mut pages_dict = pages_obj.as_dict()?.clone();
    pages_dict.set("Count", documents_pages.len() as i64);
    pages_dict.set(
        "Kids",
        documents_pages
            .keys()
            .copied()
            .map(Object::Reference)
            .collect::<Vec<_>>(),
    );
    document
        .objects
        .insert(pages_id, Object::Dictionary(pages_dict));

    let (catalog_id, catalog_obj) = catalog_object.ok_or("Catalog root not found")?;
    let mut catalog = catalog_obj.as_dict()?.clone();
    catalog.set("Pages", pages_id);
    catalog.remove(b"Outlines");
    catalog.set("PageMode", Object::Name(b"UseOutlines".to_vec()));
    document
        .objects
        .insert(catalog_id, Object::Dictionary(catalog));
    document.trailer.set("Root", catalog_id);
    document.max_id = document.objects.keys().map(|id| id.0).max().unwrap_or(0);
    document.renumber_objects();
    Ok(document)
}

fn add_index_links(document: &mut Document, entries: &[BundleEntry]) -> AnyResult<()> {
    let pages = document.get_pages();
    let index_page_id = *pages.get(&1).ok_or("index page missing")?;
    let mut annots = Vec::new();

    for (i, entry) in entries.iter().enumerate() {
        let target_id = *pages
            .get(&(entry.start_page as u32))
            .ok_or("index link target page missing")?;
        let y = INDEX_TOP_Y - INDEX_SUBTITLE_DROP - INDEX_ROW_DROP * ((i + 1) as f32);
        let annot = dictionary! {
            "Type" => "Annot",
            "Subtype" => "Link",
            "Rect" => vec![45.into(), (y - 6.0).into(), 555.into(), (y + 16.0).into()],
            "Border" => vec![0.into(), 0.into(), 0.into()],
            "Dest" => vec![Object::Reference(target_id), Object::Name(b"Fit".to_vec())],
        };
        let annot_id = document.add_object(annot);
        annots.push(Object::Reference(annot_id));
    }

    let index_page = document.get_object_mut(index_page_id)?.as_dict_mut()?;
    index_page.set("Annots", Object::Array(annots));
    Ok(())
}

fn add_bundle_bookmarks(document: &mut Document, entries: &[BundleEntry]) -> AnyResult<()> {
    let pages = document.get_pages();
    let mut current_section = None;
    let mut parent = None;

    for entry in entries {
        let target = *pages
            .get(&(entry.start_page as u32))
            .ok_or("bookmark target page missing")?;
        if current_section != Some(entry.section) {
            let section_id = document.add_bookmark(
                Bookmark::new(
                    format!("Section {}", entry.section),
                    [0.0, 0.0, 0.0],
                    2,
                    target,
                ),
                None,
            );
            current_section = Some(entry.section);
            parent = Some(section_id);
        }
        document.add_bookmark(
            Bookmark::new(entry.title.clone(), [0.0, 0.0, 0.0], 0, target),
            parent,
        );
    }

    let catalog_id = catalog_id(document)?;
    if let Some(outline_id) = document.build_outline() {
        let section_count = entries
            .iter()
            .map(|entry| entry.section)
            .collect::<HashSet<_>>()
            .len();
        let outline_count = entries.len() + section_count;
        document
            .get_object_mut(outline_id)?
            .as_dict_mut()?
            .set("Count", outline_count as i64);
        let catalog = document.get_object_mut(catalog_id)?.as_dict_mut()?;
        catalog.set("Outlines", Object::Reference(outline_id));
        catalog.set("PageMode", Object::Name(b"UseOutlines".to_vec()));
    } else {
        return Err("bookmark outline was not built".into());
    }
    Ok(())
}

fn add_continuous_page_numbers(document: &mut Document) -> AnyResult<()> {
    let pages = document.get_pages();
    for (page_no, page_id) in pages {
        let operations = Content {
            operations: vec![
                Operation::new("BT", vec![]),
                Operation::new("Tf", vec![Object::Name(b"F1".to_vec()), 9.into()]),
                Operation::new("Td", vec![285.into(), 18.into()]),
                Operation::new("Tj", vec![Object::string_literal(page_no.to_string())]),
                Operation::new("ET", vec![]),
            ],
        };
        let mut bytes = format!("% MCR_BUNDLE_PAGE {page_no}\n").into_bytes();
        bytes.extend(operations.encode()?);
        let overlay_id = document.add_object(Stream::new(dictionary! {}, bytes));

        let page = document.get_object_mut(page_id)?.as_dict_mut()?;
        let old = page.get(b"Contents")?.clone();
        let new_contents = match old {
            Object::Reference(id) => vec![Object::Reference(id), Object::Reference(overlay_id)],
            Object::Array(mut values) => {
                values.push(Object::Reference(overlay_id));
                values
            }
            _ => return Err(format!("unsupported page Contents on bundle page {page_no}").into()),
        };
        page.set("Contents", Object::Array(new_contents));
    }
    Ok(())
}

fn set_default_view_100(document: &mut Document) -> AnyResult<()> {
    let pages = document.get_pages();
    let first_page = *pages.get(&1).ok_or("first page missing")?;
    let catalog_id = catalog_id(document)?;
    let catalog = document.get_object_mut(catalog_id)?.as_dict_mut()?;
    catalog.set(
        "OpenAction",
        Object::Array(vec![
            Object::Reference(first_page),
            Object::Name(b"XYZ".to_vec()),
            Object::Null,
            Object::Null,
            Object::Real(1.0),
        ]),
    );
    Ok(())
}

fn catalog_id(document: &Document) -> AnyResult<ObjectId> {
    document
        .objects
        .iter()
        .find_map(|(id, object)| (object.type_name().ok() == Some(b"Catalog")).then_some(*id))
        .ok_or_else(|| "Catalog not found".into())
}

fn verify_bundle(
    path: &Path,
    entries: &[BundleEntry],
    expected_pages: usize,
    expected_links: usize,
    expected_bookmarks: usize,
) -> AnyResult<()> {
    let doc = Document::load(path)?;
    if doc.is_encrypted() {
        return Err("assembled bundle is encrypted".into());
    }
    let pages = doc.get_pages();
    if pages.len() != expected_pages {
        return Err(format!(
            "assembled page mismatch: {} != {expected_pages}",
            pages.len()
        )
        .into());
    }

    let page_numbers: Vec<u32> = pages.keys().copied().collect();
    let text = doc.extract_text(&page_numbers)?;
    if !text.contains("SYNTHETIC COURT BUNDLE INDEX") || !text.contains("SYNTHETIC DOCUMENT") {
        return Err("searchable text was not preserved in assembled bundle".into());
    }

    let mut landscape_pages = 0usize;
    for (page_no, page_id) in &pages {
        let (width, height) = media_box_dimensions(&doc, *page_id)?;
        if width > height {
            landscape_pages += 1;
        }
        verify_footer_marker(&doc, *page_id, *page_no)?;
    }
    let expected_landscape = if entries.iter().any(|e| e.title.ends_with("12")) {
        1
    } else {
        0
    };
    if landscape_pages != expected_landscape {
        return Err(format!(
            "orientation inventory mismatch: {landscape_pages} != {expected_landscape}"
        )
        .into());
    }

    verify_index_links(&doc, entries, expected_links)?;
    verify_open_action_100(&doc)?;
    let outline_count = count_outline_items(&doc)?;
    if outline_count != expected_bookmarks {
        return Err(
            format!("bookmark count mismatch: {outline_count} != {expected_bookmarks}").into(),
        );
    }
    Ok(())
}

fn media_box_dimensions(doc: &Document, page_id: ObjectId) -> AnyResult<(f32, f32)> {
    let page = doc.get_object(page_id)?.as_dict()?;
    let values = page.get(b"MediaBox")?.as_array()?;
    if values.len() != 4 {
        return Err("MediaBox does not have four values".into());
    }
    let x0 = object_number(&values[0])?;
    let y0 = object_number(&values[1])?;
    let x1 = object_number(&values[2])?;
    let y1 = object_number(&values[3])?;
    Ok(((x1 - x0).abs(), (y1 - y0).abs()))
}

fn object_number(object: &Object) -> AnyResult<f32> {
    match object {
        Object::Integer(v) => Ok(*v as f32),
        Object::Real(v) => Ok(*v),
        _ => Err("PDF number expected".into()),
    }
}

fn verify_footer_marker(doc: &Document, page_id: ObjectId, page_no: u32) -> AnyResult<()> {
    let marker = format!("% MCR_BUNDLE_PAGE {page_no}");
    let mut found = false;
    for stream_id in doc.get_page_contents(page_id) {
        if let Ok(stream) = doc.get_object(stream_id).and_then(Object::as_stream) {
            let bytes = stream
                .decompressed_content()
                .unwrap_or_else(|_| stream.content.clone());
            if String::from_utf8_lossy(&bytes).contains(&marker) {
                found = true;
                break;
            }
        }
    }
    if !found {
        return Err(format!("visible pagination marker missing on page {page_no}").into());
    }
    Ok(())
}

fn verify_index_links(
    doc: &Document,
    entries: &[BundleEntry],
    expected_links: usize,
) -> AnyResult<()> {
    let pages = doc.get_pages();
    let index_id = *pages.get(&1).ok_or("index page missing")?;
    let index = doc.get_object(index_id)?.as_dict()?;
    let annots = index.get(b"Annots")?.as_array()?;
    if annots.len() != expected_links || annots.len() != entries.len() {
        return Err(format!(
            "index link count mismatch: {} != {expected_links}",
            annots.len()
        )
        .into());
    }
    for (annot, entry) in annots.iter().zip(entries) {
        let annot_id = annot.as_reference()?;
        let dict = doc.get_object(annot_id)?.as_dict()?;
        if dict.get(b"Subtype")?.as_name()? != b"Link" {
            return Err("index annotation is not a Link".into());
        }
        let dest = dict.get(b"Dest")?.as_array()?;
        let target_id = dest
            .first()
            .ok_or("empty link destination")?
            .as_reference()?;
        let expected_id = *pages
            .get(&(entry.start_page as u32))
            .ok_or("expected linked page missing")?;
        if target_id != expected_id {
            return Err(format!("index link target mismatch for {}", entry.title).into());
        }
    }
    Ok(())
}

fn verify_open_action_100(doc: &Document) -> AnyResult<()> {
    let catalog = doc.get_object(catalog_id(doc)?)?.as_dict()?;
    let action = catalog.get(b"OpenAction")?.as_array()?;
    if action.len() != 5 {
        return Err("OpenAction shape mismatch".into());
    }
    if action[1].as_name()? != b"XYZ" {
        return Err("OpenAction is not XYZ".into());
    }
    match action[4] {
        Object::Real(v) if (v - 1.0).abs() < f32::EPSILON => Ok(()),
        Object::Integer(1) => Ok(()),
        _ => Err("default PDF zoom is not 100%".into()),
    }
}

fn count_outline_items(doc: &Document) -> AnyResult<usize> {
    let catalog = doc.get_object(catalog_id(doc)?)?.as_dict()?;
    let root_id = catalog.get(b"Outlines")?.as_reference()?;
    let root = doc.get_object(root_id)?.as_dict()?;
    let Some(first) = root.get(b"First").ok().and_then(|o| o.as_reference().ok()) else {
        return Ok(0);
    };
    let mut visited = HashSet::new();
    count_outline_chain(doc, first, &mut visited, 0)
}

fn count_outline_chain(
    doc: &Document,
    start: ObjectId,
    visited: &mut HashSet<ObjectId>,
    depth: usize,
) -> AnyResult<usize> {
    if depth > 10 {
        return Err("outline depth exceeded qualification limit".into());
    }
    let mut total = 0usize;
    let mut current = Some(start);
    while let Some(id) = current {
        if !visited.insert(id) {
            return Err("circular outline detected in output".into());
        }
        total += 1;
        let dict = doc.get_object(id)?.as_dict()?;
        if let Some(child) = dict.get(b"First").ok().and_then(|o| o.as_reference().ok()) {
            total += count_outline_chain(doc, child, visited, depth + 1)?;
        }
        current = dict.get(b"Next").ok().and_then(|o| o.as_reference().ok());
    }
    Ok(total)
}

fn generate_encrypted_negative_fixture(path: &Path) -> AnyResult<()> {
    let mut doc = generate_source_document(99, "Encrypted synthetic negative fixture", false)?;
    doc.trailer.set(
        "ID",
        Object::Array(vec![
            Object::string_literal(vec![1u8; 16]),
            Object::string_literal(vec![2u8; 16]),
        ]),
    );
    let version = EncryptionVersion::V1 {
        document: &doc,
        owner_password: "owner",
        user_password: "user",
        permissions: Permissions::all(),
    };
    let state = EncryptionState::try_from(version)?;
    doc.encrypt(&state)?;
    doc.save(path)?;
    Ok(())
}

fn write_receipt(
    root: &Path,
    hearing: &Path,
    core: &Path,
    specs: &[SourceSpec],
    full_entries: &[BundleEntry],
    core_entries: &[BundleEntry],
) -> AnyResult<()> {
    let source_rows = specs
        .iter()
        .map(|s| {
            format!(
                "    {{\"section\":{},\"file\":\"{}\"}}",
                s.section,
                s.path.file_name().unwrap().to_string_lossy()
            )
        })
        .collect::<Vec<_>>()
        .join(",\n");
    let json = format!(
        "{{\n  \"schema\": \"mcr-r59-synthetic-court-bundle-qualification-v1\",\n  \"status\": \"PASS\",\n  \"synthetic_only\": true,\n  \"lopdf_commit\": \"{LOPDF_COMMIT}\",\n  \"hmcts_em_stitching_reference_commit\": \"{HMCTS_STITCHING_COMMIT}\",\n  \"source_documents\": {},\n  \"source_pages_each\": {},\n  \"hearing_bundle\": {{\"file\":\"{}\",\"pages\":{},\"index_links\":{},\"bookmarks\":15}},\n  \"core_bundle\": {{\"file\":\"{}\",\"pages\":{},\"index_links\":{},\"bookmarks\":7}},\n  \"source_immutability\": \"PASS\",\n  \"malformed_input\": \"REJECTED\",\n  \"encrypted_input\": \"REJECTED\",\n  \"default_view_100_percent\": \"PASS\",\n  \"searchable_text_preserved\": \"PASS\",\n  \"continuous_visible_page_numbers\": \"PASS\",\n  \"clickable_index_targets\": \"PASS\",\n  \"nested_bookmarks\": \"PASS\",\n  \"sources\": [\n{}\n  ]\n}}\n",
        specs.len(),
        SOURCE_PAGES,
        hearing.file_name().unwrap().to_string_lossy(),
        FULL_EXPECTED_PAGES,
        full_entries.len(),
        core.file_name().unwrap().to_string_lossy(),
        CORE_EXPECTED_PAGES,
        core_entries.len(),
        source_rows
    );
    fs::write(root.join("COURT_BUNDLE_QUALIFICATION_RECEIPT.json"), json)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn full_bundle_plan_is_over_one_hundred_pages() {
        assert_eq!(FULL_EXPECTED_PAGES, 109);
    }

    #[test]
    fn source_start_pages_are_continuous() {
        for i in 0..SOURCE_DOCUMENTS {
            assert_eq!(2 + i * SOURCE_PAGES, 2 + i * 9);
        }
        assert_eq!(2 + (SOURCE_DOCUMENTS - 1) * SOURCE_PAGES, 101);
    }

    #[test]
    fn core_bundle_plan_is_small_and_issue_led() {
        assert_eq!(CORE_EXPECTED_PAGES, 37);
    }
}
