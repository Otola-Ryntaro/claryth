"""Static accessibility contracts for the Chrome side panel."""

from pathlib import Path
import re


HTML = Path("extension/src/sidepanel.html").read_text(encoding="utf-8")
CSS = Path("extension/src/sidepanel.css").read_text(encoding="utf-8")


def test_clinical_status_is_persistent_and_announced() -> None:
    assert 'id="clinical-warning" class="clinical-status pending"' in HTML
    assert 'aria-live="polite"' in HTML
    assert 'aria-atomic="true"' in HTML
    assert 'id="clinical-status-title"' in HTML
    assert 'id="clinical-status-message"' in HTML


def test_form_controls_have_labels_and_descriptions() -> None:
    assert '<label for="target-select">' in HTML
    assert '<label for="drug-input">' in HTML
    assert 'id="drug-input-help"' in HTML
    assert 'aria-describedby="drug-input-help clinical-status-message"' in HTML


def test_critical_text_is_not_below_twelve_pixels() -> None:
    sizes = [int(value) for value in re.findall(r"font-size:\s*(\d+)px", CSS)]
    assert sizes
    assert min(sizes) >= 12


def test_focus_narrow_width_and_high_contrast_rules_exist() -> None:
    assert ":focus-visible" in CSS
    assert "outline: 3px solid" in CSS
    assert "@media (max-width: 360px)" in CSS
    assert "@media (max-width: 220px)" in CSS
    assert "@media (forced-colors: active)" in CSS
