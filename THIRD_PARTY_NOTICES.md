# Third-Party Notices

This file is a working beta notice, not a substitute for legal review.

## Current App Stack

Brake's main user-facing desktop app is Electron + React. The Python backend owns detection, state, services, lockouts, recovery, and commitment logic.

PyQt6 is still present in the repository for the existing lockout window, uninstall/recovery guard UI, and legacy/reference GUI files. It is not the main app shell anymore.

Before distributing a packaged commercial binary, review every dependency license and confirm the final packaging path. In particular, do not ship proprietary PyQt6 binaries without understanding Riverbank's GPL/commercial terms or replacing those remaining PyQt surfaces.

## Runtime Dependencies

Based on local package metadata in the current development environment:

- NudeNet: MIT
- ONNX Runtime: MIT
- Transformers: Apache-2.0
- Torch: BSD-3-Clause
- Electron: MIT
- React: MIT
- Vite: MIT
- Lucide React: ISC
- PyQt6: GPL/commercial licensing applies through Riverbank/PyQt terms; currently used by lockout/guard/legacy UI surfaces
- Pillow: HPND-style/PIL license
- mss: MIT
- pywin32: PSF-style
- psutil: BSD-3-Clause
- argon2-cffi: MIT
- cryptography: Apache-2.0/BSD-style dual license
- PyYAML: MIT

Before a serious commercial release, review every dependency license and include full license texts as required.

## ML Models

- `Falconsai/nsfw_image_detection` is listed on HuggingFace as Apache-2.0.
- NudeNet package metadata reports MIT.

The beta install path does not intentionally vendor the HuggingFace model cache. The model may download on first use through Transformers/HuggingFace.
