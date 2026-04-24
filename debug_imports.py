#!/usr/bin/env python
"""Debug import chain to find neo4j dependency."""
import traceback
import sys

try:
    print("Attempting to import extract_brand_signals...")
    from agent_adapters import extract_brand_signals
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    
    print("\n" + "="*70)
    print("Note: neo4j module is not installed.")
    print("This is from graph module (Neo4j database for knowledge graphs).")
    print("It's optional - agent_adapters works without it for basic tests.")
    print("="*70)
