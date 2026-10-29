from datetime import datetime

from hkexradar.models import AnnouncementRaw
from hkexradar.normalizer import (
    link_revisions,
    merge_duplicates,
    normalize_all,
    normalize_row,
    parse_category,
    parse_size,
)


def _raw(**overrides) -> AnnouncementRaw:
    base = dict(
        news_id="12325368",
        stock_code="01407",
        stock_name="交運燃氣",
        published_at=datetime(2026, 9, 8, 22, 59),
        title="控股股東質押股份解除公告",
        category_label="公告及通告 - [內幕消息]",
        file_type="PDF",
        file_info="131KB",
        file_link="/listedco/listconews/sehk/2026/0908/2026090801276_c.pdf",
    )
    base.update(overrides)
    return AnnouncementRaw(**base)


def test_parse_category_unescapes_html_and_splits_tags():
    group, tags = parse_category("財務報表&#x2f;環境、社會及管治資料 - [中期 / 半年度報告]")
    assert group == "財務報表/環境、社會及管治資料"
    assert tags == ["中期", "半年度報告"]


def test_parse_category_without_bracket():
    group, tags = parse_category("委任代表表格")
    assert group == "委任代表表格"
    assert tags == []


def test_parse_size_units():
    assert parse_size("131KB") == 131 * 1024
    assert parse_size("1.5MB") == int(1.5 * 1024 * 1024)
    assert parse_size("") is None


def test_normalize_splits_multi_counter_codes():
    ann = normalize_row(_raw(stock_code="00700<br/>80700", stock_name="騰訊控股<br/>騰訊控股－Ｒ"))
    assert ann.primary_code == "00700"
    assert ann.alt_codes == ["80700"]
    assert ann.stock_name == "騰訊控股"
    assert ann.file_url.startswith("https://www1.hkexnews.hk/")
    assert ann.file_bytes == 131 * 1024


def test_revision_is_flagged_not_merged():
    ann = normalize_row(_raw(title="控股股東質押股份解除公告（經修訂）"))
    assert ann.is_revision is True


def test_link_revisions_points_to_original():
    original = normalize_row(_raw(news_id="1", title="年度業績公告"))
    revised = normalize_row(
        _raw(
            news_id="2",
            title="年度業績公告（經修訂）",
            published_at=datetime(2026, 9, 8, 23, 10),
        )
    )
    link_revisions([original, revised])
    assert revised.revision_of == "1"
    assert original.revision_of is None


def test_merge_duplicates_shares_file_url():
    first = normalize_row(_raw(news_id="1", stock_code="00700"))
    second = normalize_row(
        _raw(
            news_id="2",
            stock_code="80700",
            file_link="/listedco/listconews/sehk/2026/0908/2026090801276_c.pdf",
        )
    )
    merged = merge_duplicates([first, second])
    assert len(merged) == 1
    assert merged[0].alt_codes == ["80700"]


def test_normalize_all_sorts_by_time():
    later = _raw(
        news_id="2",
        published_at=datetime(2026, 9, 8, 23, 0),
        file_link="/listedco/listconews/sehk/2026/0908/2_c.pdf",
    )
    earlier = _raw(
        news_id="1",
        published_at=datetime(2026, 9, 8, 9, 0),
        file_link="/listedco/listconews/sehk/2026/0908/1_c.pdf",
    )
    result = normalize_all([later, earlier])
    assert [a.news_id for a in result] == ["1", "2"]
