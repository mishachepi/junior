#!/bin/bash

echo "Running test with Python debugger (pdb)..."
echo "Use 'b <line>' to set breakpoint"
echo "Use 'c' to continue, 'n' for next, 's' for step"
echo "----------------------------------------"

# Run with pdb
python3 -m pdb -m pytest tests/test_integration.py::test_post_review_comment_integration -v -s

# Alternative: Run standalone debug script with pdb
# python3 -m pdb debug_integration_test.py