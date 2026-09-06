from pathlib import Path
import os

src = Path(os.environ["MCR_R2_SRC"])
path = src / "tests" / "core_integration.rs"
text = path.read_text(encoding="utf-8")
old = "    assert_eq!(empty.size, 0);\n"
new = "    assert_eq!(empty.size_bytes, 0);\n"
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one R2.2 StoredObject size field repair target; found {count}")
path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
print("PASS: corrected R2.2 test to StoredObject.size_bytes")
