"""Cross-encoder contracts without model downloads or inference dependencies."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import threading
import time

import numpy as np
import pytest

from backend.services import screening_reranker as reranking


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    monkeypatch.setattr(reranking, "_cache", {})
    monkeypatch.setattr(reranking, "settings", SimpleNamespace(
        screening_reranker_model="test/model", screening_reranker_local_only=True,
        screening_reranker_batch_size=2,
    ))


def test_load_once_and_configuration_changes_have_distinct_cache(monkeypatch):
    loader = Mock(return_value=Mock())
    monkeypatch.setattr(reranking, "_load_cross_encoder", loader)
    with ThreadPoolExecutor(max_workers=4) as executor:
        adapters = list(executor.map(lambda _: reranking.get_reranker(), range(8)))
    assert all(adapter is adapters[0] for adapter in adapters)
    assert adapters[0].model_name == "test/model"
    loader.assert_called_once_with("test/model", True)
    reranking.settings.screening_reranker_local_only = False
    assert reranking.get_reranker() is not adapters[0]
    assert loader.call_args.args == ("test/model", False)


def test_missing_local_model_propagates_and_is_not_cached(monkeypatch):
    loader = Mock(side_effect=OSError("Model not cached"))
    monkeypatch.setattr(reranking, "_load_cross_encoder", loader)
    with pytest.raises(OSError, match="not cached"):
        reranking.get_reranker()
    loader.assert_called_once_with("test/model", True)
    assert reranking._cache == {}


def test_loader_disables_network_and_remote_code(monkeypatch):
    import sys
    constructor = Mock()
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=constructor))
    reranking._load_cross_encoder("local/model", True)
    constructor.assert_called_once_with("local/model", local_files_only=True, trust_remote_code=False, max_length=512)


def test_batch_order_and_bounded_inputs():
    model = Mock()
    model.predict.side_effect = [np.array([.4, -.1]), np.array([[.9]])]
    adapter = reranking.ScreeningReranker("test/model", model)
    pairs = [("a" * 6000, "b" * 6000), ("short", "c" * 6000), ("third", "evidence")]
    assert adapter.predict(pairs) == [.4, -.1, .9]
    assert [len(call.args[0]) for call in model.predict.call_args_list] == [2, 1]
    first, second = model.predict.call_args_list[0].args[0]
    assert len(first[0]) == 2000 and len(first[1]) == 2000
    assert second[0] == "short" and len(second[1]) == 3995
    assert pairs[0][0] == "a" * 6000  # Caller evidence is never mutated.
    assert model.predict.call_args.kwargs == {"batch_size": 2, "show_progress_bar": False, "convert_to_numpy": True}


@pytest.mark.parametrize("output", [[float("nan")], [float("inf")], [], [.1, .2], [[.1, .2]], 1])
def test_invalid_model_output_is_rejected(output):
    adapter = reranking.ScreeningReranker("test", Mock(predict=Mock(return_value=output)))
    with pytest.raises(ValueError, match="invalid scores"):
        adapter.predict([("requirement", "evidence")])


@pytest.mark.parametrize("pairs", [[("a",)], [("a", None)], ["ab"], [(1, "b")]])
def test_invalid_pairs_are_rejected(pairs):
    model = Mock()
    with pytest.raises(ValueError, match="pairs of text"):
        reranking.ScreeningReranker("test", model).predict(pairs)
    model.predict.assert_not_called()


def test_empty_and_oversized_requests_do_not_call_model():
    model = Mock()
    adapter = reranking.ScreeningReranker("test", model)
    assert adapter.predict([]) == []
    with pytest.raises(ValueError, match="at most 6000"):
        adapter.predict([("a", "b")] * 6001)
    model.predict.assert_not_called()


@pytest.mark.parametrize("configured, expected", [(0, 1), (999, 64)])
def test_batch_size_is_bounded(configured, expected):
    reranking.settings.screening_reranker_batch_size = configured
    model = Mock(predict=Mock(side_effect=lambda pairs, **_: [0.] * len(pairs)))
    reranking.ScreeningReranker("test", model).predict([("a", "b")] * 65)
    assert max(len(call.args[0]) for call in model.predict.call_args_list) == expected


def test_shared_model_predictions_never_overlap():
    state_lock = threading.Lock()
    active = 0
    peak = 0

    def predict(pairs, **_):
        nonlocal active, peak
        with state_lock:
            active += 1
            peak = max(peak, active)
        time.sleep(.01)
        with state_lock:
            active -= 1
        return [float(pairs[0][0])]

    adapter = reranking.ScreeningReranker("test", SimpleNamespace(predict=predict))
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda index: adapter.predict([(str(index), "evidence")]), range(8)))
    assert results == [[float(index)] for index in range(8)]
    assert peak == 1
