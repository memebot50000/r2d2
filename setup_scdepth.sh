#!/bin/bash
set -e

echo "=== Cloning ONNX-SCDepth-Monocular-Depth-Estimation repo ==="
if [ ! -d "ONNX-SCDepth-Monocular-Depth-Estimation" ]; then
    git clone https://github.com/ibaiGorordo/ONNX-SCDepth-Monocular-Depth-Estimation.git
fi

echo "=== Copying your inference.py into the repo ==="
cp inference.py ONNX-SCDepth-Monocular-Depth-Estimation/inference.py

cd ONNX-SCDepth-Monocular-Depth-Estimation

# Download the PyTorch model if not present (example for NYU, adjust URL if needed)
if [ ! -f "sc_depth_v3_nyu.pth" ]; then
    echo "Downloading PyTorch model (NYU) ..."
    wget -O sc_depth_v3_nyu.pth https://github.com/JiawangBian/sc_depth_pl/releases/download/v3/sc_depth_v3_nyu.pth
fi

echo "=== Exporting ONNX model ==="
python inference.py

echo "=== Simplifying ONNX model ==="
onnxsim sc_depth_v3_nyu.onnx sc_depth_v3_nyu_sim.onnx

cd ..

echo "=== Copying ONNX model to models/ directory ==="
mkdir -p models
cp ONNX-SCDepth-Monocular-Depth-Estimation/sc_depth_v3_nyu_sim.onnx models/

echo "=== SC-Depth ONNX setup complete! ==="
echo "Model is ready at models/sc_depth_v3_nyu_sim.onnx."
