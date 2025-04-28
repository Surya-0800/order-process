/**
 * Dashboard Tab Functions
 * 
 * This file contains the functions for handling tab switching and displaying 
 * content for the Pick, Pack, and Dispatch tabs in the PDF Management Dashboard.
 */

/**
 * Displays picklists for the Pick tab
 */
function displayPicklists() {
  const contentDiv = document.getElementById('status-content');
  contentDiv.innerHTML = '<div class="loading-indicator">Loading picklists...</div>';
  
  fetchWithErrorHandling(getApiUrl('picklists/get_picklists/'))
  .then(data => {
      // Define status order for sorting
      const statusOrder = {
          'CREATED': 1,
          'PRINTED': 2,
          'PACKING': 3
      };
      
      // Sort the data by status and then by created_at date
      data.sort((a, b) => {
          const statusCompare = (statusOrder[a.status] || 999) - (statusOrder[b.status] || 999);
          if (statusCompare !== 0) return statusCompare;
          return new Date(b.created_at) - new Date(a.created_at);
      });
      
      // Filter picklists
      const filteredPicklists = data.filter(p => 
          p.status === 'CREATED' || p.status === 'PRINTED'
      );
      
      if (filteredPicklists.length === 0) {
          contentDiv.innerHTML = '<div class="card"><p class="text-center">No picklists available for picking</p></div>';
          return;
      }
      
      // Create a basic table structure without custom styles
      let html = `
          <div class="picklist-header">
              <h3>Picklists</h3>
          </div>
          <table class="status-table">
              <thead>
                  <tr>
                      <th>Picklist ID</th>
                      <th>Type of Picklist</th>
                      <th>Qty of Picklist</th>
                      <th>Platform</th>
                      <th>Status</th>
                  </tr>
              </thead>
              <tbody>
      `;
      
      filteredPicklists.forEach(picklist => {
          const statusClass = `status-${picklist.status.toLowerCase()}`;
          
          html += `
              <tr>
                  <td>
                      <a href="javascript:void(0)" onclick="redirectToPicklistDetails('${picklist.picklist_id}')" class="picklist-link">
                          ${picklist.picklist_id}
                      </a>
                  </td>
                  <td>${picklist.picklist_type}</td>
                  <td>${picklist.quantity}</td>
                  <td>${picklist.platform}</td>
                  <td><span class="status-badge ${statusClass}">${picklist.status}</span></td>
              </tr>
          `;
      });
      
      html += `
              </tbody>
          </table>
      `;
      
      contentDiv.innerHTML = html;
  })
  .catch(error => {
      console.error('Error fetching picklists:', error);
      contentDiv.innerHTML = '<div class="card"><p class="text-center">Error loading picklists. Please refresh.</p></div>';
  });
}

/**
* Displays picklists for the Pack tab
*/
function displayPackingPicklists() {
  const contentDiv = document.getElementById('status-content');
  contentDiv.innerHTML = '<div class="loading-indicator">Loading packing picklists...</div>';
  
  fetchWithErrorHandling(getApiUrl('picklists/get_picklists/'))
  .then(data => {
      // Filter picklists to show only those with PACKING status
      const packingPicklists = data.filter(p => p.status === 'PACKING');
      
      if (packingPicklists.length === 0) {
          contentDiv.innerHTML = `
              <div class="card">
                  <p class="text-center">No picklists available for packing</p>
                  <p class="text-center"><a href="/pack/" class="btn btn-primary">Go to Packing Interface</a></p>
              </div>
          `;
          return;
      }
      
      let html = `
          <div class="picklist-header">
              <h3>Picklists Ready for Packing</h3>
              <a href="/pack/" class="btn btn-primary">Go to Packing Interface</a>
          </div>
          <table class="status-table">
              <thead>
                  <tr>
                      <th>Picklist ID</th>
                      <th>Type of Picklist</th>
                      <th>Qty of Picklist</th>
                      <th>Platform</th>
                      <th>Status</th>
                      <th>Actions</th>
                  </tr>
              </thead>
              <tbody>
      `;
      
      packingPicklists.forEach(picklist => {
          html += `
              <tr>
                  <td>
                      <a href="/picklist/${picklist.picklist_id}/" class="picklist-link">
                          ${picklist.picklist_id}
                      </a>
                  </td>
                  <td>${picklist.picklist_type}</td>
                  <td>${picklist.quantity}</td>
                  <td>${picklist.platform}</td>
                  <td><span class="status-badge status-packing">${picklist.status}</span></td>
                  <td>
                      <button class="btn btn-primary" onclick="startPacking('${picklist.picklist_id}')">
                          Pack Now
                      </button>
                  </td>
              </tr>
          `;
      });
      
      html += `
              </tbody>
          </table>
      `;
      
      contentDiv.innerHTML = html;
  })
  .catch(error => {
      console.error('Error fetching packing picklists:', error);
      contentDiv.innerHTML = `
          <div class="card">
              <p class="text-center">Error loading picklists. Please refresh.</p>
          </div>
      `;
  });
}

/**
* Displays completed picklists for the Dispatch tab
*/
function displayCompletedPicklists() {
  const contentDiv = document.getElementById('status-content');
  contentDiv.innerHTML = '<div class="loading-indicator">Loading completed picklists...</div>';
  
  fetchWithErrorHandling(getApiUrl('picklists/get_picklists/'))
  .then(data => {
      // Filter picklists to show only those with COMPLETED status
      const completedPicklists = data.filter(p => p.status === 'COMPLETED');
      
      if (completedPicklists.length === 0) {
          contentDiv.innerHTML = '<div class="card"><p class="text-center">No completed picklists available</p></div>';
          return;
      }
      
      let html = `
          <div class="picklist-header">
              <h3>Completed Picklists</h3>
          </div>
          <table class="status-table">
              <thead>
                  <tr>
                      <th>Picklist ID</th>
                      <th>Type of Picklist</th>
                      <th>Qty of Picklist</th>
                      <th>Platform</th>
                      <th>Status</th>
                  </tr>
              </thead>
              <tbody>
      `;
      
      completedPicklists.forEach(picklist => {
          html += `
              <tr>
                  <td>
                      <a href="/picklist/${picklist.picklist_id}/" class="picklist-link">
                          ${picklist.picklist_id}
                      </a>
                  </td>
                  <td>${picklist.picklist_type}</td>
                  <td>${picklist.quantity}</td>
                  <td>${picklist.platform}</td>
                  <td><span class="status-badge status-completed">COMPLETED</span></td>
              </tr>
          `;
      });
      
      html += `
              </tbody>
          </table>
      `;
      
      contentDiv.innerHTML = html;
  })
  .catch(error => {
      console.error('Error fetching completed picklists:', error);
      contentDiv.innerHTML = '<div class="card"><p class="text-center">Error loading picklists. Please refresh.</p></div>';
  });
}

/**
* Redirect to picklist details page
* @param {string} picklistId - The picklist ID to view
*/
function redirectToPicklistDetails(picklistId) {
  window.location.href = `/picklist/${picklistId}/`;
}

/**
* Start packing a picklist
* @param {string} picklistId - The picklist ID to pack
*/
function startPacking(picklistId) {
  window.location.href = `/pack/?picklist_id=${picklistId}`;
}

/**
* Setup tab click handlers
*/
function setupTabHandlers() {
  document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', function() {
          // Update UI for selected tab
          document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
          this.classList.add('active');
          
          // Update current status
          window.currentStatus = this.dataset.status;
          
          // Handle content display based on selected tab
          switch(window.currentStatus) {
              case 'Ready to Process':
                  updateOrderStatusTable(window.currentStatus);
                  break;
              case 'Pick':
                  displayPicklists();
                  break;
              case 'Pack':
                  displayPackingPicklists();
                  break;
              case 'Dispatch':
                  displayCompletedPicklists();
                  break;
              default:
                  updateOrderStatusTable(window.currentStatus);
                  break;
          }
      });
  });
}

/**
* Initialize tab functionality when document is ready
*/
document.addEventListener('DOMContentLoaded', function() {
  // Setup tab handlers
  setupTabHandlers();
  
  // Initialize with the active tab
  const activeTab = document.querySelector('.tab.active');
  if (activeTab) {
      window.currentStatus = activeTab.dataset.status;
      
      if (window.currentStatus === 'Pick') {
          displayPicklists();
      } else if (window.currentStatus === 'Pack') {
          displayPackingPicklists();
      } else if (window.currentStatus === 'Dispatch') {
          displayCompletedPicklists();
      } else {
          updateOrderStatusTable(window.currentStatus);
      }
  }
});