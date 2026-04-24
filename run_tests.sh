#!/bin/bash

echo "🧪 Marketing Platform Integration Tests"
echo "========================================"
echo ""

# Detect Python 3.10+ for Instagram
PYTHON_CMD="python3"
if [ -f "/opt/homebrew/bin/python3" ]; then
    PY_VERSION=$(/opt/homebrew/bin/python3 --version 2>&1 | awk '{print $2}')
    echo "✅ Found Homebrew Python: $PY_VERSION at /opt/homebrew/bin/python3"
    PYTHON_INSTA="/opt/homebrew/bin/python3"
else
    PYTHON_INSTA="python3"
fi

# Check system Python version
SYSTEM_PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "📌 System Python: $SYSTEM_PY_VERSION at $(which python3)"
echo ""

# Function to run test
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "🧪 Running: $test_name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    eval "$test_cmd"
    
    if [ $? -eq 0 ]; then
        echo "✅ $test_name PASSED"
    else
        echo "❌ $test_name FAILED"
    fi
}

# Menu
echo "Select a test to run:"
echo "1. Test Runway ML API (uses system Python)"
echo "2. Test Instagram Login (requires Python 3.10+)"
echo "3. Run both tests"
echo "4. Verify Instagram session"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        run_test "Runway ML API" "python3 test_runway_api.py"
        ;;
    2)
        echo "Using: $PYTHON_INSTA"
        run_test "Instagram Login" "$PYTHON_INSTA test_instagram_login.py"
        ;;
    3)
        run_test "Runway ML API" "python3 test_runway_api.py"
        echo ""
        echo "Using: $PYTHON_INSTA"
        run_test "Instagram Login" "$PYTHON_INSTA test_instagram_login.py"
        ;;
    4)
        echo "Using: $PYTHON_INSTA"
        run_test "Instagram Session Verification" "$PYTHON_INSTA test_instagram_login.py --verify"
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🏁 Test run complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

