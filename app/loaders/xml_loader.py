import xml.etree.ElementTree as ET

from .schema import normalize_record


def load_xml(path):
    """Load orders from an XML export (e.g. a warehouse/SOAP-style system)."""
    root = ET.parse(path).getroot()
    records = []
    for order_el in root.findall("order"):
        rec = {child.tag: child.text for child in order_el}
        records.append(normalize_record(rec))
    return records
