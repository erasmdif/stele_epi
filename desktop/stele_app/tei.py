"""
Esportazione TEI-XML come *vista* del modello (non è il modello).
Le annotazioni sovrapposte sono rese in stand-off (<spanGrp>/<span>),
il testo esatto in <ab xml:space="preserve"> con offset char= in code point.
"""
from xml.sax.saxutils import escape, quoteattr
from . import models

# mappatura term_type -> elemento TEI (cfr. §25 della specifica)
TERM_TEI = {
    "person": "persName", "deity": "rs", "place": "placeName",
    "ethnonym": "orgName", "institution": "orgName",
}


def _lang_of(version):
    return version.get("language") or "und"


def export_text_version(conn, version_id):
    v = models.get_text_version(conn, version_id)
    if not v:
        raise ValueError("Text version not found.")
    doc = conn.execute("SELECT * FROM text_document WHERE id=?", (v["text_document_id"],)).fetchone()
    doc = dict(doc) if doc else {}
    anns = models.annotations_for_version(conn, version_id)
    content = v["content"] or ""

    L = ['<?xml version="1.0" encoding="UTF-8"?>']
    L.append('<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang=%s>' % quoteattr(_lang_of(v)))
    L.append("  <teiHeader><fileDesc>")
    L.append("    <titleStmt><title>%s</title></titleStmt>" % escape(doc.get("title") or "Text"))
    L.append("    <publicationStmt><p>Esportato da Stele DBMS.</p></publicationStmt>")
    L.append("    <sourceDesc><p>%s</p></sourceDesc>" % escape(doc.get("description") or "nato digitale"))
    L.append("  </fileDesc></teiHeader>")

    # stand-off: uno <spanGrp> con uno <span> per annotazione (anche discontinue)
    L.append("  <standOff><spanGrp type=\"annotations\">")
    for a in anns:
        # target: lista di anchor char= per ciascuno span
        targets = " ".join("#char=%d,%d" % (s["start_position"], s["end_position"]) for s in a["spans"])
        terms = a.get("terms", [])
        L.append('    <span xml:id=%s type=%s target=%s>' % (
            quoteattr(a["uid"]), quoteattr(a["annotation_type"]), quoteattr(targets)))
        if a.get("note"):
            L.append("      <note>%s</note>" % escape(a["note"]))
        for t in terms:
            tei_el = TERM_TEI.get(t["term_type"], "term")
            if tei_el == "rs":
                L.append('      <rs type=%s>%s</rs>' % (quoteattr(t["term_type"]), escape(t["preferred_label"])))
            else:
                L.append("      <%s>%s</%s>" % (tei_el, escape(t["preferred_label"]), tei_el))
        L.append("    </span>")
    L.append("  </spanGrp></standOff>")

    L.append("  <text><body>")
    L.append('    <ab xml:space="preserve" xml:id="txt">%s</ab>' % escape(content))
    L.append("  </body></text>")
    L.append("</TEI>")
    return "\n".join(L)
