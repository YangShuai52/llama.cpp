#!/bin/bash
# Build CANN custom transformer ops from source and install.
# Usage: build_custom_ops.sh <source_dir> <install_dir> <soc_version>
#
# <source_dir>   - directory containing the op source trees (recurrent_gated_delta_rule_v310/, common/, cmake/, etc.)
# <install_dir>  - destination directory for the installed vendor package
# <soc_version>  - target SoC (e.g., ascend310p)

set -e

SOURCE_DIR="$1"
INSTALL_DIR="$2"
SOC_VERSION="${3:-ascend310p}"

if [ -z "$SOURCE_DIR" ] || [ -z "$INSTALL_DIR" ]; then
    echo "Usage: $0 <source_dir> <install_dir> [soc_version]"
    exit 1
fi

# Source CANN environment
if [ -f /usr/local/Ascend/ascend-toolkit/set_env.sh ]; then
    source /usr/local/Ascend/ascend-toolkit/set_env.sh
fi

# Find vllm-ascend csrc build system (provides build.sh, cmake/, etc.)
VLLM_CSRC=""
for candidate in /vllm-workspace/vllm-ascend/csrc /home/*/vllm-ascend/csrc; do
    if [ -f "$candidate/build.sh" ]; then
        VLLM_CSRC="$candidate"
        break
    fi
done

if [ -z "$VLLM_CSRC" ]; then
    echo "ERROR: vllm-ascend csrc build.sh not found"
    exit 1
fi

echo "=== Building custom ops ==="
echo "Source: $SOURCE_DIR"
echo "Install: $INSTALL_DIR"
echo "SOC: $SOC_VERSION"
echo "Build system: $VLLM_CSRC"

# Set up catlass (header-only GEMM library)
export CPATH=$VLLM_CSRC/third_party/catlass/include:$CPATH

# List of ops to build for 310p
if [[ "$SOC_VERSION" == "ascend310p" ]]; then
    OPS="recurrent_gated_delta_rule_v310"
else
    OPS="recurrent_gated_delta_rule"
fi

echo "Ops to build: $OPS"

# Check if .run package already exists
EXISTING_RUN=$(find $VLLM_CSRC/build -name "cann-ops-transformer-custom*.run" 2>/dev/null | head -1)

if [ -n "$EXISTING_RUN" ]; then
    echo "Using existing .run package: $EXISTING_RUN"
else
    echo "Building from source..."
    cd $VLLM_CSRC
    bash build.sh --pkg --ops="$OPS" --soc="$SOC_VERSION" 2>&1 | tail -30
    EXISTING_RUN=$(find build -name "cann-ops-transformer-custom*.run" | head -1)
fi

if [ -z "$EXISTING_RUN" ]; then
    echo "ERROR: No .run package found after build"
    exit 1
fi

echo "Installing .run package to $INSTALL_DIR..."
rm -rf $INSTALL_DIR
mkdir -p $INSTALL_DIR
chmod +x $EXISTING_RUN
$EXISTING_RUN --install-path=$INSTALL_DIR 2>&1 | tail -10

echo "=== Verifying installation ==="
if [ -f "$INSTALL_DIR/vendors/custom_transformer/op_api/lib/libcust_opapi.so" ]; then
    echo "SUCCESS: Custom ops installed to $INSTALL_DIR"
    nm -D "$INSTALL_DIR/vendors/custom_transformer/op_api/lib/libcust_opapi.so" 2>/dev/null | grep -i RecurrentGatedDeltaRule | head -3
else
    echo "ERROR: Installation verification failed"
    exit 1
fi
