from graph import get_graph_mapper

mapper = get_graph_mapper()

# Write to SQLite
db.insert_user(user_data)

# Write to Neo4j
mapper.sync_user_to_graph(user_data)