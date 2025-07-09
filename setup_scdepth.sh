#!/bin/bash
set -e

# 1. Install required Python packages
pip install opencv-python onnxruntime numpy --break-system-packages

# 2. Clone the ONNX-SCDepth-Monocular-Depth-Estimation repo
if [ ! -d "ONNX-SCDepth-Monocular-Depth-Estimation" ]; then
    git clone https://github.com/ibaiGorordo/ONNX-SCDepth-Monocular-Depth-Estimation.git
fi

# 3. Download pre-converted ONNX model if available
MODEL_URL="https://huggingface.co/ibaiGorordo/SCDepth-ONNX/resolve/main/sc_depth_v3_nyu_sim.onnx"
MODEL_DIR="models"
MODEL_PATH="$MODEL_DIR/sc_depth_v3_nyu_sim.onnx"

mkdir -p "$MODEL_DIR"

if [ ! -f "$MODEL_PATH" ]; then
    echo "Downloading SC-Depth ONNX model..."
    wget -O "$MODEL_PATH" "$MODEL_URL" || {
        echo "Failed to download ONNX model. Please download it manually from $MODEL_URL and place it in the models/ directory.";
        exit 1;
    }
else
    echo "ONNX model already exists at $MODEL_PATH"
fi

# 4. Clean up (optional)
# rm -rf ONNX-SCDepth-Monocular-Depth-Estimation

echo "=== SC-Depth ONNX setup complete! ==="
echo "Model is ready at $MODEL_PATH." 
