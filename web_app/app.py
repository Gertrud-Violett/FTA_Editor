"""
FTA Editor Web Application
Flask backend for web-based FTA editor
"""

from flask import Flask, render_template, request, jsonify, send_file, session
from flask_session import Session
import sys
import os
import json
import tempfile
import uuid
import logging
from pathlib import Path
from datetime import datetime

# Suppress OSError warnings from cachelib when it encounters inaccessible temp files
logging.getLogger('cachelib').setLevel(logging.ERROR)

# Add parent directory to path to import core module
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from FTA_Editor_core import FTACore, sanitize_name

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
app.config['SESSION_TYPE'] = 'filesystem'

# Create dedicated session directory to avoid conflicts with other temp files
session_dir = Path(tempfile.gettempdir()) / 'fta_editor_sessions'
session_dir.mkdir(exist_ok=True)
app.config['SESSION_FILE_DIR'] = str(session_dir)
app.config['SESSION_FILE_THRESHOLD'] = 100  # Maximum number of session files

Session(app)

# Store FTACore instances per session
sessions = {}

def get_core():
    """Get or create FTACore instance for current session"""
    session_id = session.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
    
    if session_id not in sessions:
        sessions[session_id] = FTACore()
    
    return sessions[session_id]

@app.route('/')
def index():
    """Render main page"""
    return render_template('index.html')

@app.route('/api/tree', methods=['GET'])
def get_tree():
    """Get the current tree data"""
    core = get_core()
    return jsonify({
        'tree': core.get_data(),
        'metadata': {
            'title': core.title,
            'date': core.date,
            'mode': core.mode
        }
    })

@app.route('/api/metadata', methods=['POST'])
def update_metadata():
    """Update metadata (title, date, mode)"""
    core = get_core()
    data = request.json
    
    core.set_metadata(
        title=data.get('title'),
        date=data.get('date'),
        mode=data.get('mode')
    )
    
    if data.get('mode'):
        core.recalculate_probabilities()
    
    return jsonify({'success': True})

@app.route('/api/node', methods=['POST'])
def add_node():
    """Add a new node"""
    core = get_core()
    data = request.json
    
    parent_id = data.get('parent_id')
    node_data = {
        'id': data.get('id'),
        'name': sanitize_name(data.get('name', '')),
        'type': data.get('type', 'Event'),
        'probability': float(data.get('probability', 1.0)),
        'logicGate': data.get('logicGate', 'OR'),
        'notes': data.get('notes', ''),
        'links': data.get('links', []),
        'children': []
    }
    
    core.add_node_to_data(parent_id, node_data)
    core.recalculate_probabilities()
    
    return jsonify({'success': True, 'tree': core.get_data()})

@app.route('/api/node/<node_id>', methods=['PUT'])
def update_node(node_id):
    """Update an existing node"""
    core = get_core()
    data = request.json
    
    update_data = {
        'name': sanitize_name(data.get('name', '')),
        'type': data.get('type', 'Event'),
        'probability': float(data.get('probability', 1.0)),
        'logicGate': data.get('logicGate', 'OR'),
        'notes': data.get('notes', ''),
        'links': data.get('links', [])
    }
    
    core.update_node(node_id, update_data)
    core.recalculate_probabilities()
    
    return jsonify({'success': True, 'tree': core.get_data()})

@app.route('/api/node/<node_id>', methods=['DELETE'])
def delete_node(node_id):
    """Delete a node"""
    core = get_core()
    
    if node_id == 'root':
        return jsonify({'success': False, 'error': 'Cannot delete root node'}), 400
    
    core.delete_node_from_data(node_id)
    core.recalculate_probabilities()
    
    return jsonify({'success': True, 'tree': core.get_data()})

@app.route('/api/node/<node_id>', methods=['GET'])
def get_node(node_id):
    """Get details of a specific node"""
    core = get_core()
    node = core.find_node_by_id(node_id)
    
    if not node:
        return jsonify({'success': False, 'error': 'Node not found'}), 404
    
    return jsonify({'success': True, 'node': node})

@app.route('/api/nodes/list', methods=['GET'])
def get_all_nodes():
    """Get flat list of all nodes for linking"""
    core = get_core()
    nodes = core.get_all_nodes_flat()
    return jsonify({'nodes': [{'id': nid, 'name': name} for nid, name in nodes if nid]})

@app.route('/api/render', methods=['POST'])
def render_diagram():
    """Render the diagram and return image"""
    core = get_core()
    data = request.json
    hide_zero = data.get('hide_zero', False)
    high_quality = data.get('high_quality', False)
    
    viewer_path = Path(__file__).parent.parent / "src" / "json_viewer.py"
    
    try:
        # Create temporary files
        tmp_json = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8')
        export_data = core.prepare_export_data()
        json.dump(export_data, tmp_json, indent=2, ensure_ascii=False)
        tmp_json.close()
        
        tmp_png = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        tmp_png.close()
        
        # Build command
        cmd = [sys.executable, str(viewer_path), '-i', tmp_json.name, '-o', tmp_png.name]
        if hide_zero:
            cmd.append('--hide-zero')
        if high_quality:
            cmd.append('--high-quality')
        
        # Run renderer
        import subprocess
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if proc.returncode != 0:
            return jsonify({
                'success': False,
                'error': f'Render failed: {proc.stderr}'
            }), 500
        
        # Read and encode image
        import base64
        with open(tmp_png.name, 'rb') as f:
            img_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Cleanup
        os.unlink(tmp_json.name)
        os.unlink(tmp_png.name)
        
        return jsonify({
            'success': True,
            'image': f'data:image/png;base64,{img_data}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/export/json', methods=['GET'])
def export_json():
    """Export as JSON file"""
    core = get_core()
    export_data = core.prepare_export_data()
    
    tmp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8')
    json.dump(export_data, tmp_file, indent=2, ensure_ascii=False)
    tmp_file.close()
    
    return send_file(
        tmp_file.name,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'fta_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )

@app.route('/api/export/xml', methods=['GET'])
def export_xml():
    """Export as XML file"""
    core = get_core()
    
    tmp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.xml', encoding='utf-8')
    tmp_file.close()
    
    success, error = core.export_to_xml(tmp_file.name)
    
    if not success:
        return jsonify({'success': False, 'error': error}), 500
    
    return send_file(
        tmp_file.name,
        mimetype='application/xml',
        as_attachment=True,
        download_name=f'fta_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xml'
    )

@app.route('/api/export/excel', methods=['GET'])
def export_excel():
    """Export as Excel file"""
    core = get_core()
    
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    tmp_file.close()
    
    success, error = core.export_to_excel(tmp_file.name)
    
    if not success:
        return jsonify({'success': False, 'error': error}), 500
    
    return send_file(
        tmp_file.name,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'fta_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

@app.route('/api/import/json', methods=['POST'])
def import_json():
    """Import from JSON file"""
    core = get_core()
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    
    try:
        # Save to temporary file
        tmp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8')
        file.save(tmp_file.name)
        tmp_file.close()
        
        # Load into core
        success, error = core.load_from_json(tmp_file.name)
        
        os.unlink(tmp_file.name)
        
        if not success:
            return jsonify({'success': False, 'error': error}), 400
        
        return jsonify({
            'success': True,
            'tree': core.get_data(),
            'metadata': {
                'title': core.title,
                'date': core.date,
                'mode': core.mode
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/new', methods=['POST'])
def new_analysis():
    """Create a new analysis"""
    session_id = session.get('session_id')
    if session_id and session_id in sessions:
        sessions[session_id] = FTACore()
    
    core = get_core()
    
    return jsonify({
        'success': True,
        'tree': core.get_data(),
        'metadata': {
            'title': core.title,
            'date': core.date,
            'mode': core.mode
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
