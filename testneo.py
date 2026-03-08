from graph import get_graph_client

def test_connection():
    client = get_graph_client()
    assert client.connected, "Not connected to Neo4j"
    print("✅ Connection test passed")

def test_query():
    client = get_graph_client()
    results = client.query("RETURN 1 as test")
    assert len(results) > 0, "Query failed"
    print("✅ Query test passed")

def test_write():
    client = get_graph_client()
    affected = client.execute_write(
        "CREATE (n:TestNode {test: 'data'}) RETURN n"
    )
    assert affected > 0, "Write failed"
    print("✅ Write test passed")

def test_schema():
    client = get_graph_client()
    summary = client.get_graph_summary()
    print(f"✅ Schema test passed")
    print(f"   Total nodes: {summary.get('total_nodes', 0)}")
    print(f"   Total relationships: {summary.get('total_relationships', 0)}")

if __name__ == "__main__":
    test_connection()
    test_query()
    test_write()
    test_schema()