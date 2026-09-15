from .json_loader import load_json
from .xml_loader import load_xml
from .csv_loader import load_csv
from .xlsx_loader import load_xlsx
from .html_scraper_loader import load_html

__all__ = ["load_json", "load_xml", "load_csv", "load_xlsx", "load_html"]
