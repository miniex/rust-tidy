import io

import pytest

from rust_tidy.diag import Reporter


@pytest.fixture
def reporter() -> Reporter:
    return Reporter(stream=io.StringIO(), color_mode="never")


@pytest.fixture
def captured(reporter: Reporter) -> io.StringIO:
    return reporter.stream  # type: ignore[return-value]
