// State management
let currentTree = null;
let selectedNodeId = null;
let allNodes = [];
let currentLinks = [];
let editingNodeId = null;
let expandedNodes = new Set(); // Track expanded/collapsed state

// Zoom and pan state
let zoomLevel = 1.0;
let panX = 0;
let panY = 0;
let isDragging = false;
let dragStartX = 0;
let dragStartY = 0;
let lastPanX = 0;
let lastPanY = 0;

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    initializeEventListeners();
    initializeDiagramControls();
    initializeResizablePanels();
    loadTree();
});

function initializeEventListeners() {
    document.getElementById('mode-select').addEventListener('change', updateMetadata);
    document.getElementById('title-input').addEventListener('change', updateMetadata);
    document.getElementById('date-input').addEventListener('change', updateMetadata);
    document.getElementById('hide-zero-checkbox').addEventListener('change', refreshDiagram);
    document.getElementById('link-search').addEventListener('input', filterAvailableNodes);
}

function initializeDiagramControls() {
    const viewport = document.getElementById('diagram-viewport');
    const container = document.getElementById('diagram-container');
    
    // Zoom controls
    document.getElementById('zoom-in-btn').addEventListener('click', () => zoomDiagram(0.2));
    document.getElementById('zoom-out-btn').addEventListener('click', () => zoomDiagram(-0.2));
    document.getElementById('zoom-reset-btn').addEventListener('click', resetZoom);
    document.getElementById('refresh-diagram-btn').addEventListener('click', refreshDiagram);
    
    // Mouse wheel zoom
    container.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        zoomDiagram(delta, e.clientX, e.clientY);
    }, { passive: false });
    
    // Pan with mouse drag
    viewport.addEventListener('mousedown', (e) => {
        if (e.button === 0) { // Left click only
            isDragging = true;
            dragStartX = e.clientX;
            dragStartY = e.clientY;
            lastPanX = panX;
            lastPanY = panY;
            viewport.classList.add('dragging');
            e.preventDefault();
        }
    });
    
    document.addEventListener('mousemove', (e) => {
        if (isDragging) {
            const deltaX = e.clientX - dragStartX;
            const deltaY = e.clientY - dragStartY;
            panX = lastPanX + deltaX;
            panY = lastPanY + deltaY;
            updateDiagramTransform();
        }
    });
    
    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            viewport.classList.remove('dragging');
        }
    });
}

function zoomDiagram(delta, clientX, clientY) {
    const viewport = document.getElementById('diagram-viewport');
    const container = document.getElementById('diagram-container');
    const oldZoom = zoomLevel;
    
    zoomLevel = Math.max(0.1, Math.min(5.0, zoomLevel + delta));
    
    // Zoom towards mouse position
    if (clientX !== undefined && clientY !== undefined) {
        const rect = container.getBoundingClientRect();
        const x = clientX - rect.left;
        const y = clientY - rect.top;
        
        const scale = zoomLevel / oldZoom;
        panX = x - (x - panX) * scale;
        panY = y - (y - panY) * scale;
    }
    
    updateDiagramTransform();
}

function resetZoom() {
    zoomLevel = 1.0;
    panX = 0;
    panY = 0;
    updateDiagramTransform();
}

function updateDiagramTransform() {
    const viewport = document.getElementById('diagram-viewport');
    viewport.style.transform = `translate(${panX}px, ${panY}px) scale(${zoomLevel})`;
}

function initializeResizablePanels() {
    // Resize tree panel (horizontal)
    const treePanel = document.querySelector('.tree-panel');
    const treeHandle = treePanel.querySelector('.resize-handle-right');
    let isResizingTree = false;
    let startXTree = 0;
    let startWidthTree = 0;
    
    treeHandle.addEventListener('mousedown', (e) => {
        isResizingTree = true;
        startXTree = e.clientX;
        startWidthTree = treePanel.offsetWidth;
        treePanel.classList.add('resizing');
        e.preventDefault();
    });
    
    // Resize details panel (vertical)
    const detailsPanel = document.querySelector('.details-panel');
    const detailsHandle = detailsPanel.querySelector('.resize-handle-top');
    let isResizingDetails = false;
    let startYDetails = 0;
    let startHeightDetails = 0;
    
    detailsHandle.addEventListener('mousedown', (e) => {
        isResizingDetails = true;
        startYDetails = e.clientY;
        startHeightDetails = detailsPanel.offsetHeight;
        detailsPanel.classList.add('resizing');
        e.preventDefault();
    });
    
    // Global mouse move handler
    document.addEventListener('mousemove', (e) => {
        if (isResizingTree) {
            const deltaX = e.clientX - startXTree;
            const newWidth = Math.max(300, Math.min(800, startWidthTree + deltaX));
            treePanel.style.flexBasis = newWidth + 'px';
            treePanel.style.flexGrow = '0';
            treePanel.style.flexShrink = '0';
        }
        
        if (isResizingDetails) {
            const deltaY = e.clientY - startYDetails;
            const newHeight = Math.max(80, Math.min(400, startHeightDetails - deltaY));
            detailsPanel.style.height = newHeight + 'px';
        }
    });
    
    // Global mouse up handler
    document.addEventListener('mouseup', () => {
        if (isResizingTree) {
            isResizingTree = false;
            treePanel.classList.remove('resizing');
        }
        if (isResizingDetails) {
            isResizingDetails = false;
            detailsPanel.classList.remove('resizing');
        }
    });
}

// API calls
async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json'
        }
    };
    
    if (data) {
        options.body = JSON.stringify(data);
    }
    
    const response = await fetch(endpoint, options);
    return await response.json();
}

// Load tree data
async function loadTree() {
    try {
        const data = await apiCall('/api/tree');
        currentTree = data.tree;
        
        // Update metadata fields
        document.getElementById('mode-select').value = data.metadata.mode;
        document.getElementById('title-input').value = data.metadata.title;
        document.getElementById('date-input').value = data.metadata.date;
        
        // Update tree label
        document.getElementById('tree-label').textContent = 
            data.metadata.mode === 'ETA' ? 'Event Tree' : 'Fault Tree';
        
        renderTree();
        refreshDiagram();
    } catch (error) {
        console.error('Failed to load tree:', error);
    }
}

// Render tree view
function renderTree() {
    const container = document.getElementById('tree-container');
    container.innerHTML = '';
    
    if (currentTree) {
        // Initialize root as expanded
        if (!expandedNodes.has('root')) {
            expandedNodes.add('root');
        }
        renderNode(currentTree, container, 0, null);
    }
}

function renderNode(node, container, level, parentId) {
    const div = document.createElement('div');
    const nodeId = node.id;
    
    // Calculate color class (cycles through 4 colors)
    const colorLevel = level % 4;
    div.className = `tree-node level${colorLevel}`;
    div.dataset.nodeId = nodeId;
    div.dataset.level = level;
    
    // Set indent based on level (20px per level)
    const indent = level * 20 + 10;
    div.style.paddingLeft = `${indent}px`;
    
    // Check if parent is collapsed
    if (parentId && !expandedNodes.has(parentId)) {
        div.classList.add('collapsed');
    }
    
    // Create expand/collapse button if node has children
    const hasChildren = node.children && node.children.length > 0;
    const toggleBtn = document.createElement('span');
    toggleBtn.className = 'tree-toggle';
    
    if (hasChildren) {
        const isExpanded = expandedNodes.has(nodeId);
        toggleBtn.textContent = isExpanded ? '−' : '+';
        toggleBtn.onclick = (e) => {
            e.stopPropagation();
            toggleNodeExpansion(nodeId);
        };
    } else {
        toggleBtn.classList.add('empty');
    }
    
    div.appendChild(toggleBtn);
    
    // Create content span
    const contentSpan = document.createElement('span');
    contentSpan.className = 'tree-node-content';
    
    // Add probability markers
    const prob = node.probability;
    if (prob === 0.0) {
        div.classList.add('zero-prob');
        contentSpan.innerHTML = '<span class="node-mark">✖</span>';
    } else if (prob === 1.0 && !hasChildren) {
        div.classList.add('full-prob');
    }
    
    contentSpan.innerHTML += node.name || node.id;
    div.appendChild(contentSpan);
    
    // Click to select
    div.addEventListener('click', (e) => {
        e.stopPropagation();
        selectNode(node.id);
    });
    
    // Highlight if selected
    if (node.id === selectedNodeId) {
        div.classList.add('selected');
    }
    
    container.appendChild(div);
    
    // Render children
    if (hasChildren) {
        node.children.forEach(child => renderNode(child, container, level + 1, nodeId));
    }
}

function toggleNodeExpansion(nodeId) {
    if (expandedNodes.has(nodeId)) {
        // Collapse: remove this node and all descendants from expanded set
        expandedNodes.delete(nodeId);
        collapseAllDescendants(nodeId);
    } else {
        expandedNodes.add(nodeId);
    }
    renderTree();
}

function collapseAllDescendants(nodeId) {
    // Find the node in the tree and collapse all its descendants
    const node = findNodeById(currentTree, nodeId);
    if (node && node.children) {
        node.children.forEach(child => {
            expandedNodes.delete(child.id);
            collapseAllDescendants(child.id);
        });
    }
}

function findNodeById(node, targetId) {
    if (node.id === targetId) {
        return node;
    }
    if (node.children) {
        for (const child of node.children) {
            const found = findNodeById(child, targetId);
            if (found) return found;
        }
    }
    return null;
}

// Select node
async function selectNode(nodeId) {
    selectedNodeId = nodeId;
    renderTree();
    
    try {
        const response = await apiCall(`/api/node/${nodeId}`);
        if (response.success) {
            displayNodeDetails(response.node);
        }
    } catch (error) {
        console.error('Failed to load node details:', error);
    }
}

function displayNodeDetails(node) {
    const container = document.getElementById('details-content');
    const calcProb = node.calculatedProbability || node.probability || 0.0;
    
    let linksText = '';
    if (node.links) {
        node.links.forEach(link => {
            linksText += `${link.relation} -> ${link.target_id}\n`;
        });
    }
    
    container.textContent = `Name: ${node.name || ''}
Type: ${node.type || ''}
Base Probability: ${node.probability || 0.0}
Logic Gate: ${node.logicGate || ''}
Calculated Probability: ${calcProb}
Node ID: ${node.id || ''}

Notes:
${node.notes || ''}

Links:
${linksText}`;
}

// Metadata update
async function updateMetadata() {
    const data = {
        mode: document.getElementById('mode-select').value,
        title: document.getElementById('title-input').value,
        date: document.getElementById('date-input').value
    };
    
    try {
        await apiCall('/api/metadata', 'POST', data);
        document.getElementById('tree-label').textContent = 
            data.mode === 'ETA' ? 'Event Tree' : 'Fault Tree';
        loadTree();
    } catch (error) {
        console.error('Failed to update metadata:', error);
    }
}

// Diagram rendering
async function refreshDiagram() {
    const container = document.getElementById('diagram-container');
    const img = document.getElementById('diagram-image');
    const loading = document.getElementById('diagram-loading');
    const error = document.getElementById('diagram-error');
    
    img.classList.remove('loaded');
    loading.style.display = 'block';
    error.classList.remove('show');
    
    try {
        const hideZero = document.getElementById('hide-zero-checkbox').checked;
        const response = await apiCall('/api/render', 'POST', {
            hide_zero: hideZero,
            high_quality: false
        });
        
        if (response.success) {
            img.src = response.image;
            img.classList.add('loaded');
            resetZoom(); // Reset zoom when new diagram loads
        } else {
            throw new Error(response.error);
        }
    } catch (err) {
        error.textContent = 'Failed to render diagram: ' + err.message;
        error.classList.add('show');
    } finally {
        loading.style.display = 'none';
    }
}

async function renderHighQuality() {
    const hideZero = document.getElementById('hide-zero-checkbox').checked;
    try {
        const response = await apiCall('/api/render', 'POST', {
            hide_zero: hideZero,
            high_quality: true
        });
        
        if (response.success) {
            // Download the image
            const link = document.createElement('a');
            link.href = response.image;
            link.download = `fta_diagram_${new Date().getTime()}.png`;
            link.click();
        }
    } catch (error) {
        alert('Failed to render high-quality image: ' + error.message);
    }
}

// Node operations
async function showAddNodeDialog() {
    if (!selectedNodeId) {
        alert('Please select a parent node first');
        return;
    }
    
    editingNodeId = null;
    document.getElementById('dialog-title').textContent = 'Add Node';
    document.getElementById('node-form').reset();
    currentLinks = [];
    
    await loadAvailableNodes();
    updateLinksList();
    
    document.getElementById('node-dialog').classList.add('show');
}

async function showEditNodeDialog() {
    if (!selectedNodeId) {
        alert('Please select a node to edit');
        return;
    }
    
    try {
        const response = await apiCall(`/api/node/${selectedNodeId}`);
        if (!response.success) {
            alert('Failed to load node');
            return;
        }
        
        editingNodeId = selectedNodeId;
        const node = response.node;
        
        document.getElementById('dialog-title').textContent = 'Edit Node';
        document.getElementById('node-name').value = node.name || '';
        document.getElementById('node-type').value = node.type || 'Event';
        document.getElementById('node-probability').value = node.probability || 1.0;
        document.getElementById('node-logic-gate').value = node.logicGate || 'OR';
        document.getElementById('node-notes').value = node.notes || '';
        
        currentLinks = node.links || [];
        
        await loadAvailableNodes();
        updateLinksList();
        
        document.getElementById('node-dialog').classList.add('show');
    } catch (error) {
        alert('Failed to load node: ' + error.message);
    }
}

function closeNodeDialog() {
    document.getElementById('node-dialog').classList.remove('show');
}

async function saveNodeDialog() {
    const name = document.getElementById('node-name').value;
    const type = document.getElementById('node-type').value;
    const probability = parseFloat(document.getElementById('node-probability').value);
    const logicGate = document.getElementById('node-logic-gate').value;
    const notes = document.getElementById('node-notes').value;
    
    if (!name || probability < 0 || probability > 1) {
        alert('Please fill in all required fields correctly');
        return;
    }
    
    const nodeData = {
        name,
        type,
        probability,
        logicGate,
        notes,
        links: currentLinks
    };
    
    try {
        if (editingNodeId) {
            // Update existing node
            const response = await apiCall(`/api/node/${editingNodeId}`, 'PUT', nodeData);
            if (response.success) {
                currentTree = response.tree;
                renderTree();
                refreshDiagram();
                closeNodeDialog();
            }
        } else {
            // Add new node
            nodeData.parent_id = selectedNodeId;
            nodeData.id = `${selectedNodeId}_${Date.now()}`;
            
            const response = await apiCall('/api/node', 'POST', nodeData);
            if (response.success) {
                currentTree = response.tree;
                renderTree();
                refreshDiagram();
                closeNodeDialog();
            }
        }
    } catch (error) {
        alert('Failed to save node: ' + error.message);
    }
}

async function deleteNode() {
    if (!selectedNodeId || selectedNodeId === 'root') {
        alert('Cannot delete root node');
        return;
    }
    
    if (!confirm('Are you sure you want to delete this node?')) {
        return;
    }
    
    try {
        const response = await apiCall(`/api/node/${selectedNodeId}`, 'DELETE');
        if (response.success) {
            currentTree = response.tree;
            selectedNodeId = null;
            renderTree();
            refreshDiagram();
            document.getElementById('details-content').textContent = 'Select a node to view details';
        }
    } catch (error) {
        alert('Failed to delete node: ' + error.message);
    }
}

// Links management
async function loadAvailableNodes() {
    try {
        const response = await apiCall('/api/nodes/list');
        allNodes = response.nodes;
        filterAvailableNodes();
    } catch (error) {
        console.error('Failed to load nodes:', error);
    }
}

function filterAvailableNodes() {
    const search = document.getElementById('link-search').value.toLowerCase();
    const select = document.getElementById('available-nodes');
    select.innerHTML = '';
    
    allNodes.forEach(node => {
        if (!search || `${node.name} (${node.id})`.toLowerCase().includes(search)) {
            const option = document.createElement('option');
            option.value = node.id;
            option.textContent = `${node.name} (${node.id})`;
            select.appendChild(option);
        }
    });
}

function addANDLink() {
    addLink('AND');
}

function addORLink() {
    addLink('OR');
}

function addLink(relation) {
    const select = document.getElementById('available-nodes');
    const selectedOptions = Array.from(select.selectedOptions);
    
    selectedOptions.forEach(option => {
        const targetId = option.value;
        if (!currentLinks.find(l => l.target_id === targetId && l.relation === relation)) {
            currentLinks.push({ target_id: targetId, relation });
        }
    });
    
    updateLinksList();
}

function removeLink(targetId, relation) {
    currentLinks = currentLinks.filter(l => 
        !(l.target_id === targetId && l.relation === relation)
    );
    updateLinksList();
}

function updateLinksList() {
    const andList = document.getElementById('and-links-list');
    const orList = document.getElementById('or-links-list');
    
    andList.innerHTML = '';
    orList.innerHTML = '';
    
    currentLinks.forEach(link => {
        const node = allNodes.find(n => n.id === link.target_id);
        const nodeName = node ? `${node.name} (${link.target_id})` : link.target_id;
        
        const li = document.createElement('li');
        li.innerHTML = `
            ${nodeName}
            <button onclick="removeLink('${link.target_id}', '${link.relation}')">Remove</button>
        `;
        
        if (link.relation === 'AND') {
            andList.appendChild(li);
        } else {
            orList.appendChild(li);
        }
    });
}

// File operations
async function newAnalysis() {
    if (!confirm('Create new analysis? Unsaved changes will be lost.')) {
        return;
    }
    
    try {
        await apiCall('/api/new', 'POST');
        loadTree();
    } catch (error) {
        alert('Failed to create new analysis: ' + error.message);
    }
}

function loadJSON() {
    document.getElementById('file-input').click();
}

async function handleFileLoad(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/import/json', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        if (data.success) {
            loadTree();
        } else {
            alert('Failed to load file: ' + data.error);
        }
    } catch (error) {
        alert('Failed to load file: ' + error.message);
    }
}

async function saveJSON() {
    window.location.href = '/api/export/json';
}

async function exportXML() {
    window.location.href = '/api/export/xml';
}

async function exportExcel() {
    window.location.href = '/api/export/excel';
}
