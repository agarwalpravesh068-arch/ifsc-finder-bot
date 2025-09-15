

import os
import pandas as pd
import mysql.connector
from flask import Flask, render_template_string, send_file
from io import BytesIO

app = Flask(__name__)

# MySQL Config (from env variables)
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Queries Log Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .download-btn {
            margin: 20px 0;
            padding: 10px 15px;
            background: green;
            color: white;
            text-decoration: none;
            border-radius: 5px;
        }
    </style>
</head>
<body>
    <h2>📊 Queries Log Dashboard</h2>
    <a href="/download" class="download-btn">⬇ Download CSV</a>
    <table>
        <tr>
            {% for col in columns %}
            <th>{{ col }}</th>
            {% endfor %}
        </tr>
        {% for row in rows %}
        <tr>
            {% for item in row %}
            <td>{{ item }}</td>
            {% endfor %}
        </tr>
        {% endfor %}
    </table>
</body>
</html>
"""

def get_data():
    conn = mysql.connector.connect(**DB_CONFIG)
    query = "SELECT * FROM queries_log ORDER BY id DESC LIMIT 100"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

@app.route("/")
def index():
    df = get_data()
    return render_template_string(HTML_TEMPLATE, columns=df.columns, rows=df.values.tolist())

@app.route("/download")
def download():
    df = get_data()
    output = BytesIO()
    df.to_csv(output, index=False)
    output.seek(0)
    return send_file(output, mimetype="text/csv", as_attachment=True, download_name="queries_log.csv")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

