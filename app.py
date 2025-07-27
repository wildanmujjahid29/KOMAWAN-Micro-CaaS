import logging
import os
import json
import time
from datetime import datetime, timedelta

import docker
import mysql.connector
from flask import Flask, flash, redirect, render_template, request, url_for, jsonify

# Inisialisasi Aplikasi Flask
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # Ganti dengan secret key yang aman

# Setup logging
logging.basicConfig(filename='activity.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s:%(message)s')

# Konfigurasi koneksi MySQL
MYSQL_CONFIG = {
    'user': 'root',         
    'password': '',         
    'host': 'localhost',
    'database': 'microiaas' 
}

def get_db():
    return mysql.connector.connect(**MYSQL_CONFIG)

# Inisialisasi tabel jika belum ada
def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Tabel riwayat dengan kolom tambahan
    c.execute('''CREATE TABLE IF NOT EXISTS riwayat (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nama_kontainer VARCHAR(255),
        penyewa VARCHAR(255),
        deskripsi TEXT,
        waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status VARCHAR(50),
        image VARCHAR(255) DEFAULT 'ubuntu:latest',
        cpu_limit VARCHAR(10) DEFAULT '1',
        memory_limit VARCHAR(10) DEFAULT '1g',
        uptime_start TIMESTAMP NULL,
        last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )''')
    
    # Tabel untuk system monitoring
    c.execute('''CREATE TABLE IF NOT EXISTS system_stats (
        id INT AUTO_INCREMENT PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        total_containers INT DEFAULT 0,
        running_containers INT DEFAULT 0,
        stopped_containers INT DEFAULT 0,
        cpu_usage DECIMAL(5,2) DEFAULT 0,
        memory_usage DECIMAL(5,2) DEFAULT 0,
        disk_usage DECIMAL(5,2) DEFAULT 0
    )''')
    
    # Tabel untuk activity logs
    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        action VARCHAR(100),
        container_name VARCHAR(255),
        user_name VARCHAR(255),
        status VARCHAR(50),
        details TEXT
    )''')
    
    conn.commit()
    c.close()
    conn.close()

init_db()

# Inisialisasi client Docker
try:
    client = docker.from_env()
except docker.errors.DockerException:
    print("Error: Pastikan Docker sudah berjalan di sistem Anda!")
    exit()

# Helper Functions
def log_activity(action, container_name="", user_name="", status="success", details=""):
    """Log activity ke database"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO activity_logs (action, container_name, user_name, status, details) 
                     VALUES (%s, %s, %s, %s, %s)''',
                  (action, container_name, user_name, status, details))
        conn.commit()
        c.close()
        conn.close()
    except Exception as e:
        logging.error(f"Failed to log activity: {e}")

def get_container_stats(container):
    """Get container resource usage statistics"""
    try:
        stats = container.stats(stream=False)
        
        # Calculate CPU percentage
        cpu_percent = 0
        if 'cpu_stats' in stats and 'precpu_stats' in stats:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * len(stats['cpu_stats']['cpu_usage']['percpu_usage']) * 100
        
        # Calculate memory usage
        memory_usage = 0
        memory_limit = 0
        if 'memory_stats' in stats:
            memory_usage = stats['memory_stats'].get('usage', 0)
            memory_limit = stats['memory_stats'].get('limit', 0)
        
        # Calculate network I/O
        network_rx = 0
        network_tx = 0
        if 'networks' in stats:
            for interface in stats['networks'].values():
                network_rx += interface.get('rx_bytes', 0)
                network_tx += interface.get('tx_bytes', 0)
        
        return {
            'cpu_percent': round(cpu_percent, 1),
            'memory_usage': f"{memory_usage // (1024*1024)}MB" if memory_usage else "0MB",
            'memory_percent': round((memory_usage / memory_limit) * 100, 1) if memory_limit else 0,
            'network_rx': f"{network_rx // (1024*1024)}MB",
            'network_tx': f"{network_tx // (1024*1024)}MB"
        }
    except Exception as e:
        logging.error(f"Error getting container stats: {e}")
        return {
            'cpu_percent': 0,
            'memory_usage': "0MB",
            'memory_percent': 0,
            'network_rx': "0MB",
            'network_tx': "0MB"
        }

def update_system_stats():
    """Update system statistics"""
    try:
        containers = client.containers.list(all=True)
        running_containers = len([c for c in containers if c.status == 'running'])
        stopped_containers = len([c for c in containers if c.status == 'exited'])
        
        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT INTO system_stats (total_containers, running_containers, stopped_containers) 
                     VALUES (%s, %s, %s)''',
                  (len(containers), running_containers, stopped_containers))
        conn.commit()
        c.close()
        conn.close()
    except Exception as e:
        logging.error(f"Error updating system stats: {e}")

# Routes
@app.route('/', methods=['GET', 'POST'])
def index():
    search = request.args.get('search', '').strip()
    show_all = request.args.get('show_all', '0') == '1'
    status_filter = request.args.get('status_filter', '')
    
    # Get containers
    if show_all:
        containers = client.containers.list(all=True)
    else:
        containers = [c for c in client.containers.list(all=True) if c.status == 'running']
    
    # Apply search filter
    if search:
        containers = [c for c in containers if search.lower() in c.name.lower()]
    
    # Apply status filter
    if status_filter:
        containers = [c for c in containers if c.status == status_filter]
    
    # Add stats to containers
    for container in containers:
        container.stats_data = get_container_stats(container)
        # Calculate uptime
        created_time = datetime.strptime(container.attrs['Created'][:19], '%Y-%m-%dT%H:%M:%S')
        container.uptime = str(datetime.now() - created_time).split('.')[0]
    
    # Get riwayat from database
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM riwayat ORDER BY waktu DESC LIMIT 50')
    riwayat = c.fetchall()
    
    # Get recent activity logs
    c.execute('SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT 10')
    activity_logs = c.fetchall()
    
    c.close()
    conn.close()
    
    # Update system stats
    update_system_stats()
    
    return render_template('index.html', 
                         containers=containers, 
                         riwayat=riwayat,
                         activity_logs=activity_logs,
                         search=search, 
                         show_all=show_all,
                         status_filter=status_filter)

@app.route('/create', methods=['POST'])
def create_container():
    nama_kontainer = request.form.get('nama_kontainer')
    penyewa = request.form.get('penyewa')
    deskripsi = request.form.get('deskripsi')
    image = request.form.get('image', 'ubuntu:latest')
    cpu_limit = request.form.get('cpu_limit', '1')
    memory_limit = request.form.get('memory', '1g')
    
    if not nama_kontainer or not penyewa:
        flash('Nama kontainer dan penyewa wajib diisi!', 'danger')
        return redirect(url_for('index'))
    
    try:
        # Check if name already exists
        for c in client.containers.list(all=True):
            if nama_kontainer == c.name:
                flash('Nama kontainer sudah digunakan!', 'danger')
                return redirect(url_for('index'))
        
        # Create container with resource limits
        container = client.containers.run(
            image,
            detach=True,
            tty=True,
            command='sleep infinity',
            name=nama_kontainer,
            mem_limit=memory_limit,
            # cpu_count=int(float(cpu_limit))  # Uncomment if Docker supports this
        )
        
        status = 'running'
        flash(f'Kontainer {nama_kontainer} berhasil dibuat!', 'success')
        logging.info(f"Kontainer {nama_kontainer} dibuat oleh {penyewa}")
        
        # Log activity
        log_activity("Container Created", nama_kontainer, penyewa, "success", 
                    f"Image: {image}, CPU: {cpu_limit}, Memory: {memory_limit}")
        
    except docker.errors.ImageNotFound:
        try:
            client.images.pull(image)
            container = client.containers.run(
                image,
                detach=True,
                tty=True,
                command='sleep infinity',
                name=nama_kontainer,
                mem_limit=memory_limit
            )
            status = 'running'
            flash(f'Kontainer {nama_kontainer} berhasil dibuat setelah pull image!', 'success')
            log_activity("Container Created", nama_kontainer, penyewa, "success", 
                        f"Image pulled and created: {image}")
        except Exception as e:
            flash(f'Gagal membuat kontainer: {e}', 'danger')
            log_activity("Container Creation Failed", nama_kontainer, penyewa, "error", str(e))
            return redirect(url_for('index'))
            
    except docker.errors.APIError as e:
        flash(f'Gagal membuat kontainer: {e}', 'danger')
        log_activity("Container Creation Failed", nama_kontainer, penyewa, "error", str(e))
        return redirect(url_for('index'))
    
    # Save to database
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO riwayat (nama_kontainer, penyewa, deskripsi, status, image, cpu_limit, memory_limit, uptime_start) 
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s)''',
              (nama_kontainer, penyewa, deskripsi, status, image, cpu_limit, memory_limit, datetime.now()))
    conn.commit()
    c.close()
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/stop/<container_id>', methods=['POST'])
def stop_container(container_id):
    try:
        container = client.containers.get(container_id)
        container.stop()
        status = 'stopped'
        flash(f'Kontainer {container.name} berhasil dihentikan.', 'success')
        logging.info(f"Kontainer {container.name} dihentikan.")
        
        # Update status in database
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE riwayat SET status=%s WHERE nama_kontainer=%s', (status, container.name))
        conn.commit()
        c.close()
        conn.close()
        
        log_activity("Container Stopped", container.name, "", "success")
        
    except docker.errors.NotFound:
        flash(f"Kontainer dengan ID {container_id} tidak ditemukan.", 'danger')
        log_activity("Container Stop Failed", "", "", "error", f"Container ID {container_id} not found")
    except Exception as e:
        flash(f'Gagal menghentikan kontainer: {e}', 'danger')
        log_activity("Container Stop Failed", "", "", "error", str(e))
    
    return redirect(url_for('index'))

@app.route('/start/<container_id>', methods=['POST'])
def start_container(container_id):
    try:
        container = client.containers.get(container_id)
        container.start()
        status = 'running'
        flash(f'Kontainer {container.name} berhasil dijalankan.', 'success')
        logging.info(f"Kontainer {container.name} dijalankan.")
        
        # Update status in database
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE riwayat SET status=%s, uptime_start=%s WHERE nama_kontainer=%s', 
                 (status, datetime.now(), container.name))
        conn.commit()
        c.close()
        conn.close()
        
        log_activity("Container Started", container.name, "", "success")
        
    except docker.errors.NotFound:
        flash(f"Kontainer dengan ID {container_id} tidak ditemukan.", 'danger')
    except Exception as e:
        flash(f'Gagal menjalankan kontainer: {e}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/restart/<container_id>', methods=['POST'])
def restart_container(container_id):
    try:
        container = client.containers.get(container_id)
        container.restart()
        flash(f'Kontainer {container.name} berhasil direstart.', 'success')
        logging.info(f"Kontainer {container.name} direstart.")
        
        # Update uptime start
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE riwayat SET uptime_start=%s WHERE nama_kontainer=%s', 
                 (datetime.now(), container.name))
        conn.commit()
        c.close()
        conn.close()
        
        log_activity("Container Restarted", container.name, "", "success")
        
    except docker.errors.NotFound:
        flash(f"Kontainer dengan ID {container_id} tidak ditemukan.", 'danger')
    except Exception as e:
        flash(f'Gagal restart kontainer: {e}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/delete/<container_id>', methods=['POST'])
def delete_container(container_id):
    try:
        container = client.containers.get(container_id)
        container_name = container.name
        container.remove(force=True)
        flash(f'Kontainer {container_name} berhasil dihapus.', 'success')
        logging.info(f"Kontainer {container_name} dihapus.")
        
        # Update status in database
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE riwayat SET status=%s WHERE nama_kontainer=%s', ('deleted', container_name))
        conn.commit()
        c.close()
        conn.close()
        
        log_activity("Container Deleted", container_name, "", "success")
        
    except docker.errors.NotFound:
        flash(f"Kontainer dengan ID {container_id} tidak ditemukan.", 'danger')
    except docker.errors.APIError as e:
        flash(f'Gagal menghapus kontainer: {e}', 'danger')
        log_activity("Container Delete Failed", "", "", "error", str(e))
    
    return redirect(url_for('index'))

@app.route('/logs/<container_id>')
def get_container_logs(container_id):
    try:
        container = client.containers.get(container_id)
        logs = container.logs(tail=100).decode('utf-8')
        return render_template('logs.html', container=container, logs=logs)
    except docker.errors.NotFound:
        flash(f"Kontainer dengan ID {container_id} tidak ditemukan.", 'danger')
        return redirect(url_for('index'))

@app.route('/api/stats/<container_id>')
def api_container_stats(container_id):
    """API endpoint untuk mendapatkan real-time stats container"""
    try:
        container = client.containers.get(container_id)
        stats = get_container_stats(container)
        return jsonify(stats)
    except docker.errors.NotFound:
        return jsonify({'error': 'Container not found'}), 404

@app.route('/api/system-stats')
def api_system_stats():
    """API endpoint untuk system statistics"""
    try:
        containers = client.containers.list(all=True)
        running = len([c for c in containers if c.status == 'running'])
        stopped = len([c for c in containers if c.status == 'exited'])
        total = len(containers)
        
        return jsonify({
            'total_containers': total,
            'running_containers': running,
            'stopped_containers': stopped,
            'pending_containers': total - running - stopped
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/bulk-action', methods=['POST'])
def bulk_action():
    """Handle bulk operations on multiple containers"""
    action = request.form.get('action')
    container_ids = request.form.getlist('container_ids')
    
    if not container_ids:
        flash('Pilih minimal satu kontainer!', 'warning')
        return redirect(url_for('index'))
    
    success_count = 0
    error_count = 0
    
    for container_id in container_ids:
        try:
            container = client.containers.get(container_id)
            
            if action == 'start':
                container.start()
            elif action == 'stop':
                container.stop()
            elif action == 'restart':
                container.restart()
            elif action == 'delete':
                container.remove(force=True)
            
            success_count += 1
            log_activity(f"Bulk {action.title()}", container.name, "", "success")
            
        except Exception as e:
            error_count += 1
            logging.error(f"Bulk {action} failed for {container_id}: {e}")
    
    if success_count > 0:
        flash(f'{success_count} kontainer berhasil di-{action}.', 'success')
    if error_count > 0:
        flash(f'{error_count} kontainer gagal di-{action}.', 'danger')
    
    return redirect(url_for('index'))

@app.route('/monitoring')
def monitoring():
    """System monitoring dashboard"""
    conn = get_db()
    c = conn.cursor()
    
    # Get system stats history
    c.execute('SELECT * FROM system_stats ORDER BY timestamp DESC LIMIT 24')
    stats_history = c.fetchall()
    
    # Get activity logs
    c.execute('SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT 50')
    activity_logs = c.fetchall()
    
    c.close()
    conn.close()
    
    return render_template('monitoring.html', 
                         stats_history=stats_history,
                         activity_logs=activity_logs)

@app.route('/backup-containers', methods=['POST'])
def backup_containers():
    """Create backup of all container configurations"""
    try:
        containers = client.containers.list(all=True)
        backup_data = []
        
        for container in containers:
            backup_data.append({
                'name': container.name,
                'image': container.image.tags[0] if container.image.tags else 'unknown',
                'status': container.status,
                'created': container.attrs['Created'],
                'config': container.attrs['Config']
            })
        
        # Save backup to file
        backup_filename = f"container_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_filename, 'w') as f:
            json.dump(backup_data, f, indent=2, default=str)
        
        flash(f'Backup berhasil dibuat: {backup_filename}', 'success')
        log_activity("Container Backup", "", "", "success", f"Backed up {len(containers)} containers")
        
    except Exception as e:
        flash(f'Gagal membuat backup: {e}', 'danger')
        log_activity("Container Backup Failed", "", "", "error", str(e))
    
    return redirect(url_for('index'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

# Menjalankan aplikasi
if __name__ == '__main__':
    app.run(debug=True, port=5001)