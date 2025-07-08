# How to create a database

1. Download the health records from your MyChart account.
2. `python importer.py mychart.db /path-to-records/*xml`

# How to inspect the database via web browser

1. `python db_to_json.py mychart.db mychart.json`
2. `open viewer.html`

