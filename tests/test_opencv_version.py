"""SPEC § 13 — Version: a 4.x wheel fails the suite immediately rather than producing
quietly different numbers, and the DNN engine in use is recorded in the record."""

from __future__ import annotations

import cv2

from secondlook import metrics


def test_opencv_is_the_5_line():
    assert cv2.__version__.startswith("5."), cv2.__version__


def test_five_x_apis_this_entry_relies_on_exist():
    assert hasattr(cv2, "CV_Bool")
    assert hasattr(cv2.dnn, "ENGINE_NEW") and hasattr(cv2.dnn, "ENGINE_CLASSIC")
    assert hasattr(cv2.dnn, "TextDetectionModel_DB")
    assert hasattr(cv2, "QRCodeDetector") and hasattr(cv2, "barcode_BarcodeDetector")
    # Removed in 5.x; their presence would mean a 4.x wheel resolved after all.
    assert not hasattr(cv2.dnn, "readNetFromCaffe")
    assert not hasattr(cv2.dnn, "readNetFromDarknet")


def test_dnn_engine_is_recorded(measure, monkeypatch):
    assert measure("clean_a").opencv_version == cv2.__version__
    assert measure("clean_a").dnn_engine == "new"
    monkeypatch.setenv("OPENCV_FORCE_DNN_ENGINE", str(int(cv2.dnn.ENGINE_CLASSIC)))
    assert metrics.dnn_engine_name() == "classic"
    monkeypatch.setenv("OPENCV_FORCE_DNN_ENGINE", "classic")
    assert metrics.dnn_engine_name() == "classic"
    monkeypatch.delenv("OPENCV_FORCE_DNN_ENGINE")
    assert metrics.dnn_engine_name() == "new"
