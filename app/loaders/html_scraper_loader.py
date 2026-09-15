from pathlib import Path

from bs4 import BeautifulSoup

from .schema import normalize_record

_COLUMNS = ["order_id", "customer", "amount", "status", "date"]


def load_html(path):
    """Scrape orders out of a legacy HTML report with no export/API of its own.

    Common in older internal portals: the only way to get the data out is to
    parse the rendered table, so this loader is the Beautiful Soup equivalent
    of the other structured-format loaders.
    """
    soup = BeautifulSoup(Path(path).read_text(), "html.parser")
    table = soup.find("table", id="orders-table")
    records = []
    for row in table.find_all("tr")[1:]:  # skip header row
        cells = [td.get_text(strip=True) for td in row.find_all("td")]
        if len(cells) != len(_COLUMNS):
            continue
        rec = dict(zip(_COLUMNS, cells))
        rec["source"] = "legacy_portal"
        records.append(normalize_record(rec))
    return records
