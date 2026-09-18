# Models

**No weights are vendored.** SPEC § 10's rule: nothing ships until its licence is read and
recorded here with the source URL and a sha256.

Measurement 5 (text presence and coverage) therefore runs the **classical path** by
default — plain OpenCV, no weights: a black-hat transform against the local paper level
gives every stroke's darkness and Weber contrast, the contrast mask is closed horizontally
into word boxes, and `connectedComponentsWithStats` reports them. The record's
`text_detector` field says `classical` so the evaluation always states which path produced
its numbers.

The DNN path (`cv2.dnn.TextDetectionModel_DB` over an ONNX detector, OpenCV 5's new DNN
engine with `OPENCV_FORCE_DNN_ENGINE` selecting the classic one) is the documented optional
enhancement. It lands only once a detector with a redistributable licence is identified,
and this file will then carry, per model:

| Model | Source URL | Licence | sha256 |
|---|---|---|---|
| _none yet_ | | | |

The record's `dnn_engine` field already reports the engine OpenCV would use, so the engine
story is measurable before any model is vendored.
