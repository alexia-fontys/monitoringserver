from flask import Flask, request, jsonify, render_template_string
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime
import pyodbc
import json
import os
import logging
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Azure SQL Database configuration
DB_SERVER = os.environ.get('DB_SERVER', 'sqldb-knowledgehub-01.database.windows.net')
DB_NAME = os.environ.get('DB_NAME', 'sql-knowledgehub-01')
DB_USER = os.environ.get('DB_USER', 'sqladmin')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'Admin1234!')

CONNECTION_STRING = (
    f'DRIVER={{ODBC Driver 18 for SQL Server}};'
    f'SERVER={DB_SERVER};'
    f'DATABASE={DB_NAME};'
    f'UID={DB_USER};'
    f'PWD={DB_PASSWORD};'
    f'Encrypt=yes;'
    f'TrustServerCertificate=no;'
    f'Connection Timeout=30;'
)

max_entries = 100

# HTML template with embedded table and charts
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>💗 PinkPulse — Monitoring Dashboard</title>
  <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --pink: #ff6b93;
      --light-pink: #ffd1dc;
      --bg: #fff5f8;
    }

    body {
      margin: 0;
      font-family: 'Nunito', sans-serif;
      background: var(--bg);
      background-image: radial-gradient(circle at top left, rgba(255,182,193,0.2), transparent 70%), 
                        radial-gradient(circle at bottom right, rgba(255,182,193,0.2), transparent 70%);
      color: #4a2c3a;
      padding: 20px;
    }

    header {
      text-align: center;
      margin-bottom: 20px;
    }

    header h1 {
      color: var(--pink);
      font-size: 2.4em;
      margin: 0;
      text-shadow: 2px 2px 0 var(--light-pink);
    }

    header p {
      color: #6a4753;
      font-size: 1em;
    }

    main {
      max-width: 1000px;
      margin: 0 auto;
      background: white;
      border-radius: 20px;
      border: 2px solid var(--light-pink);
      box-shadow: 0 8px 25px rgba(255, 107, 147, 0.15);
      padding: 30px;
      position: relative;
    }

    .stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 20px;
      margin-bottom: 25px;
    }

    .stat {
      background: linear-gradient(135deg, #ffb6c1, #ffd6e0);
      border-radius: 15px;
      color: white;
      text-align: center;
      padding: 25px;
      box-shadow: 0 6px 15px rgba(255,107,147,0.3);
    }

    .stat h3 {
      font-size: 1em;
      margin: 0 0 10px;
    }

    .stat p {
      font-size: 2em;
      margin: 0;
      font-weight: 700;
    }

    section {
      margin-top: 30px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 15px;
      font-size: 0.9em;
    }

    th, td {
      padding: 12px 15px;
      border-bottom: 1px solid #ffd1dc;
    }

    th {
      background: linear-gradient(90deg, #ff9ebb, #ffb6c1);
      color: white;
      text-align: left;
      font-weight: bold;
    }

    tr:nth-child(even) { background: #fff9fb; }
    tr:hover { background: #fff0f5; }

    .no-data {
      text-align: center;
      color: #ff9ebb;
      padding: 60px 20px;
    }

    .no-data h2 {
      font-size: 1.8em;
      margin: 0 0 10px;
    }

    .floating-heart {
      position: absolute;
      font-size: 22px;
      opacity: 0.7;
      animation: float 6s ease-in-out infinite;
    }

    @keyframes float {
      0% { transform: translateY(0) rotate(0deg); }
      50% { transform: translateY(-15px) rotate(10deg); }
      100% { transform: translateY(0) rotate(0deg); }
    }

    footer {
      text-align: center;
      color: var(--pink);
      margin-top: 25px;
      font-size: 0.9em;
    }
  </style>
</head>
<body>
  <div class="floating-heart" style="top: 10%; left: 8%;">💖</div>
  <div class="floating-heart" style="top: 40%; right: 10%;">💕</div>
  <div class="floating-heart" style="bottom: 15%; left: 15%;">🌸</div>
  <div class="floating-heart" style="bottom: 25%; right: 12%;">💗</div>

  <header>
    <h1>PinkPulse Monitoring Dashboard</h1>
    <p>Keep an eye on your systems with love and hearts 💕</p>
  </header>

  <main>
    <div class="stats">
      <div class="stat">
        <h3>Active Clients</h3>
        <p>—</p>
      </div>
      <div class="stat">
        <h3>Total Metrics</h3>
        <p>—</p>
      </div>
      <div class="stat">
        <h3>Latest CPU</h3>
        <p>—%</p>
      </div>
      <div class="stat">
        <h3>Latest RAM</h3>
        <p>—%</p>
      </div>
    </div>

    <section>
      <h2 style="color: var(--pink); border-bottom: 2px dashed var(--light-pink); display: inline-block;">Recent Metrics 📊</h2>
      <div class="no-data">
        <h2>No Metrics Yet 💫</h2>
        <p>Waiting for clients to send data...</p>
      </div>
    </section>
  </main>

  <footer>
    <p>Made with 💗 — Pink and hearts forever</p>
  </footer>
</body>
</html>
'''


# ==================== DATABASE FUNCTIONS ====================
def get_db_connection():
    """Get a database connection to Azure SQL."""
    try:
        logger.info("Attempting database connection...")
        conn = pyodbc.connect(CONNECTION_STRING)
        logger.info("✓ Database connection successful")
        return conn
    except Exception as e:
        logger.error(f"✗ Database connection failed: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def init_db():
    """Initialize the Azure SQL database tables."""
    try:
        logger.info("Starting database initialization...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        logger.info("Creating metrics table if not exists...")
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='metrics' AND xtype='U')
            CREATE TABLE metrics (
                id INT IDENTITY(1,1) PRIMARY KEY,
                client_id NVARCHAR(255) NOT NULL,
                client_name NVARCHAR(255),
                timestamp NVARCHAR(50) NOT NULL,
                received_at NVARCHAR(50) NOT NULL,
                cpu_percent FLOAT,
                gpu_percent FLOAT,
                ram_json NVARCHAR(MAX),
                ping_ms FLOAT,
                internet_connected BIT,
                raw_data NVARCHAR(MAX),
                created_at DATETIME2 DEFAULT GETDATE()
            )
        ''')
        logger.info("✓ Metrics table created/verified")
        
        logger.info("Creating index on client_id...")
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_client_id' AND object_id = OBJECT_ID('metrics'))
            CREATE INDEX idx_client_id ON metrics(client_id)
        ''')
        logger.info("✓ Index idx_client_id created/verified")
        
        logger.info("Creating index on timestamp...")
        cursor.execute('''
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_timestamp' AND object_id = OBJECT_ID('metrics'))
            CREATE INDEX idx_timestamp ON metrics(timestamp DESC)
        ''')
        logger.info("✓ Index idx_timestamp created/verified")
        
        conn.commit()
        conn.close()
        logger.info("✓ Database initialization complete")
    except Exception as e:
        logger.error(f"✗ Database initialization failed: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def insert_metric(client_id, data):
    """Insert a metric into the database."""
    try:
        logger.info(f"Inserting metric for client: {client_id}")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Extract fields
        client_name = data.get('client_name')
        timestamp = data.get('timestamp')
        received_at = data.get('received_at')
        cpu_percent = data.get('cpu_percent')
        gpu_percent = data.get('gpu_percent')
        ram = data.get('ram')
        ping_ms = data.get('ping_ms')
        internet_connected = data.get('internet_connected')
        
        ram_json = json.dumps(ram) if ram else None
        raw_data = json.dumps(data)
        
        logger.info(f"Data - CPU: {cpu_percent}%, RAM: {ram.get('percent') if ram else 'N/A'}%")
        
        cursor.execute('''
            INSERT INTO metrics 
            (client_id, client_name, timestamp, received_at, cpu_percent, gpu_percent, 
                ram_json, ping_ms, internet_connected, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (client_id, client_name, timestamp, received_at, cpu_percent, gpu_percent,
                ram_json, ping_ms, internet_connected, raw_data))
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"✗ Insert metric failed for client {client_id}: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def get_all_metrics(limit=50):
    """Get all metrics from database."""
    try:
        logger.info(f"Fetching all metrics (limit: {limit})...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT TOP (?) * FROM metrics 
            ORDER BY timestamp DESC
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        metrics = []
        for row in rows:
            metric = json.loads(row.raw_data)
            metric['client_id'] = row.client_id
            metrics.append(metric)
        
        logger.info(f"✓ Retrieved {len(metrics)} metrics")
        return metrics
    except Exception as e:
        logger.error(f"✗ Get all metrics failed: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def get_client_metrics(client_id=None, limit=20):
    """Get metrics for a specific client or all clients."""
    try:
        logger.info(f"Fetching metrics for client: {client_id or 'all'} (limit: {limit})")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if client_id:
            cursor.execute('''
                SELECT TOP (?) * FROM metrics 
                WHERE client_id = ?
                ORDER BY timestamp DESC
            ''', (limit, client_id))
        else:
            cursor.execute('''
                SELECT TOP (?) * FROM metrics 
                ORDER BY timestamp DESC
            ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        metrics = []
        for row in rows:
            metric = json.loads(row.raw_data)
            metric['client_id'] = row.client_id
            metrics.append(metric)
        
        logger.info(f"✓ Retrieved {len(metrics)} client metrics")
        return metrics
    except Exception as e:
        logger.error(f"✗ Get client metrics failed: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def get_total_clients():
    """Get count of unique clients."""
    try:
        logger.info("Counting total clients...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(DISTINCT client_id) as count FROM metrics')
        count = cursor.fetchone()[0]
        
        conn.close()
        logger.info(f"✓ Total clients: {count}")
        return count
    except Exception as e:
        logger.error(f"✗ Get total clients failed: {str(e)}")
        logger.error(traceback.format_exc())
        return 0

def get_total_metrics():
    """Get total count of metrics."""
    try:
        logger.info("Counting total metrics...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) as count FROM metrics')
        count = cursor.fetchone()[0]
        
        conn.close()
        logger.info(f"✓ Total metrics: {count}")
        return count
    except Exception as e:
        logger.error(f"✗ Get total metrics failed: {str(e)}")
        logger.error(traceback.format_exc())
        return 0

def get_client_list():
    """Get list of all clients with their info."""
    try:
        logger.info("Fetching client list...")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                client_id,
                client_name,
                MAX(timestamp) as last_seen,
                COUNT(*) as metric_count
            FROM metrics
            GROUP BY client_id, client_name
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        clients = []
        for row in rows:
            clients.append({
                'client_id': row.client_id,
                'client_name': row.client_name or row.client_id,
                'last_seen': row.last_seen,
                'metric_count': row.metric_count
            })
        
        logger.info(f"✓ Retrieved {len(clients)} clients")
        return clients
    except Exception as e:
        logger.error(f"✗ Get client list failed: {str(e)}")
        logger.error(traceback.format_exc())
        return []

# ==================== HELPER FUNCTIONS ====================
def generate_charts(metrics_list):
    """Generate matplotlib charts from metrics data."""
    try:
        logger.info(f"Generating charts from {len(metrics_list)} metrics...")
        
        if not metrics_list or len(metrics_list) < 2:
            logger.info("✓ Not enough data for charts (need at least 2 points)")
            return {}
        
        charts = {}
        
        timestamps = [m.get('timestamp', '')[-8:] for m in metrics_list]
        cpu_data = [m.get('cpu_percent', 0) for m in metrics_list if m.get('cpu_percent') is not None]
        ram_data = [m.get('ram', {}).get('percent', 0) for m in metrics_list if m.get('ram', {}).get('percent') is not None]
        
        # CPU Chart
        if cpu_data and len(cpu_data) > 1:
            logger.info("Generating CPU chart...")
            cpu_timestamps = [m.get('timestamp', '')[-8:] for m in metrics_list if m.get('cpu_percent') is not None]
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(cpu_timestamps, cpu_data, marker='o', linewidth=2, markersize=4, color='#667eea')
            ax.set_xlabel('Time')
            ax.set_ylabel('CPU Usage (%)')
            ax.set_title('CPU Usage Over Time')
            ax.grid(True, alpha=0.3)
            ax.set_ylim(0, 100)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            charts['CPU Usage'] = base64.b64encode(buf.read()).decode('utf-8')
            plt.close()
            logger.info("✓ CPU chart generated")
        
        # RAM Chart
        if ram_data and len(ram_data) > 1:
            logger.info("Generating RAM chart...")
            ram_timestamps = [m.get('timestamp', '')[-8:] for m in metrics_list if m.get('ram', {}).get('percent') is not None]
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(ram_timestamps, ram_data, marker='o', linewidth=2, markersize=4, color='#764ba2')
            ax.set_xlabel('Time')
            ax.set_ylabel('RAM Usage (%)')
            ax.set_title('RAM Usage Over Time')
            ax.grid(True, alpha=0.3)
            ax.set_ylim(0, 100)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            charts['RAM Usage'] = base64.b64encode(buf.read()).decode('utf-8')
            plt.close()
            logger.info("✓ RAM chart generated")
        
        # GPU Chart
        gpu_data = [m.get('gpu_percent') for m in metrics_list if m.get('gpu_percent') is not None]
        if gpu_data and len(gpu_data) > 1:
            logger.info("Generating GPU chart...")
            gpu_timestamps = [m.get('timestamp', '')[-8:] for m in metrics_list if m.get('gpu_percent') is not None]
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(gpu_timestamps, gpu_data, marker='o', linewidth=2, markersize=4, color='#22c55e')
            ax.set_xlabel('Time')
            ax.set_ylabel('GPU Usage (%)')
            ax.set_title('GPU Usage Over Time')
            ax.grid(True, alpha=0.3)
            ax.set_ylim(0, 100)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            charts['GPU Usage'] = base64.b64encode(buf.read()).decode('utf-8')
            plt.close()
            logger.info("✓ GPU chart generated")
        
        # Ping Chart
        ping_data = [m.get('ping_ms') for m in metrics_list if m.get('ping_ms') is not None]
        if ping_data and len(ping_data) > 1:
            logger.info("Generating Ping chart...")
            ping_timestamps = [m.get('timestamp', '')[-8:] for m in metrics_list if m.get('ping_ms') is not None]
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(ping_timestamps, ping_data, marker='o', linewidth=2, markersize=4, color='#f59e0b')
            ax.set_xlabel('Time')
            ax.set_ylabel('Ping (ms)')
            ax.set_title('Network Latency Over Time')
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=100)
            buf.seek(0)
            charts['Network Latency'] = base64.b64encode(buf.read()).decode('utf-8')
            plt.close()
            logger.info("✓ Ping chart generated")
        
        logger.info(f"✓ Generated {len(charts)} charts total")
        return charts
    except Exception as e:
        logger.error(f"✗ Chart generation failed: {str(e)}")
        logger.error(traceback.format_exc())
        return {}

# ==================== FLASK ROUTES ====================
@app.route('/')
def dashboard():
    """Display the metrics dashboard."""
    try:
        logger.info("Dashboard route accessed")
        
        all_metrics = get_all_metrics(limit=50)
        latest = all_metrics[0] if all_metrics else None
        recent_metrics = list(reversed(get_client_metrics(limit=20)))
        charts = generate_charts(recent_metrics)
        total_clients = get_total_clients()
        total_metrics = get_total_metrics()
        base_url = request.url_root.rstrip('/')
        
        logger.info("✓ Dashboard rendered successfully")
        
        return render_template_string(
            HTML_TEMPLATE,
            metrics=all_metrics,
            latest_metrics=latest,
            charts=charts,
            total_clients=total_clients,
            total_metrics=total_metrics,
            base_url=base_url
        )
    except Exception as e:
        logger.error(f"✗ Dashboard route failed: {str(e)}")
        logger.error(traceback.format_exc())
        return f"Dashboard Error: {str(e)}", 500

@app.route('/api/metrics', methods=['POST'])
def receive_metrics():
    """API endpoint to receive metrics from external monitoring clients."""
    try:
        logger.info(f"POST /api/metrics from {request.remote_addr}")
        
        data = request.get_json()
        
        if not data:
            logger.warning("✗ No data provided in request")
            return jsonify({'error': 'No data provided'}), 400
        
        data['received_at'] = datetime.now().isoformat()
        client_id = data.get('client_name') or data.get('client_id') or request.remote_addr
        
        logger.info(f"Processing metrics from client: {client_id}")
        
        insert_metric(client_id, data)
        
        logger.info(f"✓ Metrics received successfully from {client_id}")
        
        return jsonify({
            'status': 'success',
            'message': 'Metrics received',
            'client_id': client_id
        }), 200
        
    except Exception as e:
        logger.error(f"✗ Receive metrics failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    """API endpoint to retrieve stored metrics."""
    try:
        logger.info("GET /api/metrics")
        
        all_metrics = get_all_metrics(limit=1000)
        total_clients = get_total_clients()
        
        logger.info("✓ Metrics retrieved successfully")
        
        return jsonify({
            'total_entries': len(all_metrics),
            'total_clients': total_clients,
            'metrics': all_metrics
        }), 200
    except Exception as e:
        logger.error(f"✗ Get metrics API failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/api/clients', methods=['GET'])
def get_clients():
    """API endpoint to get list of connected clients."""
    try:
        logger.info("GET /api/clients")
        
        clients = get_client_list()
        
        logger.info("✓ Client list retrieved successfully")
        
        return jsonify({
            'total_clients': len(clients),
            'clients': clients
        }), 200
    except Exception as e:
        logger.error(f"✗ Get clients API failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint for Azure."""
    try:
        logger.info("Health check accessed")
        
        total_clients = get_total_clients()
        
        logger.info("✓ Health check passed")
        
        return jsonify({
            'status': 'healthy',
            'clients': total_clients,
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"✗ Health check failed: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

# ==================== MAIN ====================
if __name__ == '_main_':
    try:
        logger.info("="*60)
        logger.info("STARTING FLASK APPLICATION")
        logger.info("="*60)
        logger.info(f"Database Server: {DB_SERVER}")
        logger.info(f"Database Name: {DB_NAME}")
        logger.info(f"Database User: {DB_USER}")
        
        # Initialize database
        init_db()
        
        logger.info("Starting Flask server on 0.0.0.0:8000")
        # For local development
        port = int(os.environ.get('PORT', 8000))
        app.run(host='0.0.0.0', port=port, debug=False)
    except Exception as e:
        logger.critical(f"✗✗✗ APPLICATION STARTUP FAILED ✗✗✗")
        logger.critical(f"Error: {str(e)}")
        logger.critical(traceback.format_exc())
        raise