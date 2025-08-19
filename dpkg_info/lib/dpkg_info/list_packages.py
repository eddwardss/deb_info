import xapian
import sys

def get_pkg_name(doc):
    for term in doc.termlist():
        term_str = term.term.decode() if isinstance(term.term, bytes) else term.term
        if term_str.startswith("XP"):
            return term_str[2:]
    return None

def main(index_path):
    db = xapian.Database(index_path)
    doccount = db.get_doccount()
    names = []
    for docid in range(1, doccount + 1):
        try:
            doc = db.get_document(docid)
            name = get_pkg_name(doc)
            if name:
                names.append(name)
        except xapian.InvalidArgumentError:
            continue
    for name in sorted(names):
        print(name)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: list_packages.py <xapian_index>")
        sys.exit(1)
    main(sys.argv[1])
