"""Every link to the site names its own source, so signups can be traced back to this package."""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = [ROOT / "README.md", ROOT / "pyproject.toml", *(ROOT / "src").rglob("*.py"), *(ROOT / "examples").glob("*.*")]
LINK = re.compile(r"https://singaporemobileproxy\.com(?!/api/)[^\s\"'`)>]*")  # API endpoints aren't links


def test_every_site_link_has_a_utm_source():
    found = []
    for f in FILES:
        text = f.read_text(encoding="utf-8")
        for m in LINK.finditer(text):
            # a link split across adjacent string literals continues on the next line
            link = m.group(0)
            tail = text[m.end():m.end() + 200]
            if "utm_source=" not in link and "utm_source=" in tail.split("\n", 2)[1] if "\n" in tail else False:
                link += tail
            found.append((f.name, link))
            assert "utm_source=" in link, f"{f.name}: {m.group(0)} has no utm_source"
    assert found


def test_readme_links_are_github_tagged_so_ci_can_retag_them_for_pypi():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    links = LINK.findall(readme)
    assert links and all("utm_source=github&utm_medium=repo" in link for link in links)


def test_no_em_dashes_in_copy():
    for f in FILES:
        assert "—" not in f.read_text(encoding="utf-8"), f.name
