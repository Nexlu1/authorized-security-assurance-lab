from pathlib import Path
import os

src = Path(os.environ["MCR_R2_SRC"])
path = src / "src" / "mail.rs"
text = path.read_text(encoding="utf-8")
old = '''                let valid = if i + 1 < body.len() && body[i + 1] == b'\\n' {
                    true
                } else if i + 2 < body.len() && body[i + 1] == b'\\r' && body[i + 2] == b'\\n' {
                    true
                } else if i + 2 < body.len() {
                    body[i + 1].is_ascii_hexdigit() && body[i + 2].is_ascii_hexdigit()
                } else {
                    false
                };'''
new = '''                let soft_break = (i + 1 < body.len() && body[i + 1] == b'\\n')
                    || (i + 2 < body.len() && body[i + 1] == b'\\r' && body[i + 2] == b'\\n');
                let valid = soft_break
                    || (i + 2 < body.len()
                        && body[i + 1].is_ascii_hexdigit()
                        && body[i + 2].is_ascii_hexdigit());'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one quoted-printable Clippy cleanup target; found {count}")
path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
print("PASS: simplified quoted-printable soft-break validation for strict Clippy")
