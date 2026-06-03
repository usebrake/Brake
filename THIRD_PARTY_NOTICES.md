# Third-Party Notices

This file is a working beta notice, not a substitute for legal review.

## Release-Blocking License Note

Brake currently uses PyQt6. PyQt6 distribution is governed by Riverbank's GPL/commercial terms. A proprietary/source-available public beta installer may require either:

- a commercial PyQt license, or
- a port from PyQt6 to PySide6/LGPL, with proper LGPL compliance.

Do not treat this file as legal approval to distribute a proprietary PyQt6 build.

## Runtime Dependencies

Based on local package metadata in the current development environment:

- NudeNet: MIT
- ONNX Runtime: MIT
- Transformers: Apache-2.0
- Torch: BSD-3-Clause
- PyQt6: GPL/commercial licensing applies through Riverbank/PyQt terms; see release-blocking note above
- Pillow: HPND-style/PIL license
- mss: MIT
- pywin32: PSF-style
- psutil: BSD-3-Clause
- argon2-cffi: MIT
- PyYAML: MIT

Before a serious commercial release, review every dependency license and include full license texts as required.

## ML Models

- `Falconsai/nsfw_image_detection` is listed on HuggingFace as Apache-2.0.
- NudeNet package metadata reports MIT.

The beta packaging path does not intentionally vendor the HuggingFace model cache. The model may download on first use through Transformers/HuggingFace.
