# Native Backend Scaffold

This folder is the future native acceleration layer for Screen-AI.

Current status:

```text
scaffold only
```

Why it exists:

- show the hackathon architecture is AMD-ready
- keep CUDA/HIP differences isolated in one shim
- avoid vendor-specific conditionals in algorithm code
- preserve CPU as the default runtime

Planned files:

```text
gpu_compat.h
screen_gpu_backend.cpp
screen_gpu_backend.cu
screen_gpu_backend.h
Makefile
```

Build idea:

```bash
make cpu
make cuda CUDA_ARCH=sm_80
make hip HIP_ARCH=gfx1201
```

For the first working hackathon demo, Python/OpenCV/ONNXRuntime remains the implementation path. This native layer is the roadmap for optimized ROCm/CUDA parity.

