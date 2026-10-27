from .csv_loader import load_csv
from .generic import load_csv_records, load_json_records, load_records
from .html_scraper_loader import load_html
from .json_loader import load_json
from .xlsx_loader import load_xlsx
from .xml_loader import load_xml

__all__ = [
    "load_json", "load_xml", "load_csv", "load_xlsx", "load_html",
    "load_csv_records", "load_json_records", "load_records",
]
