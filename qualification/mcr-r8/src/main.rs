use std::env;

fn usage() {
    eprintln!(
        "mcr-ingest bootstrap\n\
         usage:\n\
           mcr-ingest self-test\n\
           mcr-ingest object-path <lowercase-sha256>\n\
           mcr-ingest archive-name <untrusted-member-name>"
    );
}

fn main() {
    let mut args = env::args().skip(1);
    match args.next().as_deref() {
        Some("self-test") => {
            let h = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
            mcr_ingest::object_store::object_relpath(h).expect("object path");
            mcr_ingest::archive_name::validate_member_name("word/document.xml")
                .expect("safe archive name");
            assert!(mcr_ingest::archive_name::validate_member_name("../escape").is_err());
            println!("bootstrap self-test PASS");
        }
        Some("object-path") => {
            let Some(hash) = args.next() else {
                usage();
                std::process::exit(2);
            };
            match mcr_ingest::object_store::object_relpath(&hash) {
                Ok(p) => println!("{}", p.display()),
                Err(e) => {
                    eprintln!("ERROR: {e}");
                    std::process::exit(1);
                }
            }
        }
        Some("archive-name") => {
            let Some(name) = args.next() else {
                usage();
                std::process::exit(2);
            };
            match mcr_ingest::archive_name::validate_member_name(&name) {
                Ok(()) => println!("SAFE"),
                Err(e) => {
                    eprintln!("REJECTED: {e}");
                    std::process::exit(1);
                }
            }
        }
        _ => {
            usage();
            std::process::exit(2);
        }
    }
}
