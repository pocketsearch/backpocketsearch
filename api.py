import os
import sqlite3
from flask import Flask, jsonify, request
from models import Roadmap, Task

app = Flask(__name__)
DATABASE = os.path.join(os.getcwd(), 'test_database.db')  # Database path

# Function to create the test database

def create_test_db():
    # Setup for the SQLite test database
    if not os.path.exists(DATABASE):
        connection = sqlite3.connect(DATABASE)
        cursor = connection.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS roadmaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT,
            deadline TEXT
        )''')
        connection.commit()
        connection.close()  

# Function to initialize database connection
def get_db():
    conn = sqlite3.connect(DATABASE)
    return conn

@app.route('/api/roadmaps', methods=['GET'])
def get_roadmaps():
    app.logger.info('Received request to get roadmaps')

    conn = get_db()
    cursor = conn.cursor()
    # Checking if table exists
    cursor.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="roadmaps"')
    if not cursor.fetchone():
        return jsonify({'error': 'Table not found'}), 404
    cursor.execute('SELECT * FROM roadmaps')
    roadmaps = cursor.fetchall()
    conn.close()
    return jsonify(roadmaps), 200

@app.route('/api/roadmaps', methods=['POST'])
def create_roadmap():
    app.logger.info('Received request to create roadmap with data: %s', request.json)

    data = request.json
    new_roadmap = Roadmap(data['title'], data['description'], data['status'], data['deadline'])
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO roadmaps (title, description, status, deadline) VALUES (?, ?, ?, ?)',
                   (new_roadmap.title, new_roadmap.description, new_roadmap.status, new_roadmap.deadline))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Roadmap created successfully!'}), 201

if __name__ == '__main__':
    create_test_db()  # Ensure tables are created before running the app
    app.run(host='0.0.0.0', port=5001, debug=True)