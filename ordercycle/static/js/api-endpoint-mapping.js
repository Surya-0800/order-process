// /**
//  * API Endpoint Mapping for PDF Management Dashboard
//  * 
//  * This script provides compatibility between old and new API endpoints
//  * to ensure that the dashboard works correctly with the backend API.
//  */

// // Define the mapping between old and new API endpoints
// const API_ENDPOINT_MAP = {
//   // Format: 'old-endpoint': 'new-endpoint'
  
//   // Picklist endpoints
//   'picklists/': 'picklists/get_picklists/',
//   'picklists/:id/': 'picklists/:id/get_picklist_items/',
//   'picklists/:id/mark-picked/': 'picklists/:id/mark_items_picked/',
//   'picklists/:id/status/': 'picklists/:id/update_status/',
//   'picklists/:id/assign-picker/': 'picklists/:id/assign_picker/',
//   'picklists/:id/undo-picked/': 'picklists/:id/undo_picked_items/',
//   'picklists/:id/mark-items-picked/': 'picklists/:id/mark_items_picked/',
//   'picklists/:id/update-status/': 'picklists/:id/update_status/',
  
//   // Order endpoints
//   'order-counts/': 'order-counts/get_counts/',
//   'single-orders/': 'order-counts/get_single_orders/',
//   'multi-orders/': 'order-counts/get_multi_orders/',
//   'process-orders/': 'order-counts/process_orders/',
  
//   // File processing endpoints
//   'pdf-uploads/': 'pdf-uploads/upload/',
//   'process-files/': 'pdf-uploads/process-files/'
// };

// /**
// * Maps an old API endpoint to a new endpoint format
// * @param {string} endpoint - The endpoint to map
// * @returns {string} The mapped endpoint
// */
// function mapApiEndpoint(endpoint) {
//   // Check if we have a direct match
//   if (API_ENDPOINT_MAP[endpoint]) {
//       return API_ENDPOINT_MAP[endpoint];
//   }
  
//   // Check for parameterized endpoints
//   for (const [oldPattern, newPattern] of Object.entries(API_ENDPOINT_MAP)) {
//       // Skip non-parameterized patterns
//       if (!oldPattern.includes(':')) continue;
      
//       // Create regex to match endpoints with parameters
//       const oldRegexStr = '^' + oldPattern.replace(/:\w+\//g, '[^/]+/') + '$';
//       const oldRegex = new RegExp(oldRegexStr);
      
//       if (oldRegex.test(endpoint)) {
//           // Extract parameters from the old endpoint
//           const paramRegex = /:([\w]+)/g;
//           let match;
//           let paramNames = [];
//           let paramValues = [];
          
//           // Extract parameter names from the pattern
//           while ((match = paramRegex.exec(oldPattern)) !== null) {
//               paramNames.push(match[1]);
//           }
          
//           // Split the endpoint by '/' to extract values
//           const endpointParts = endpoint.split('/');
//           const patternParts = oldPattern.split('/');
          
//           // Match parameters with their values
//           for (let i = 0; i < patternParts.length; i++) {
//               if (patternParts[i].startsWith(':')) {
//                   paramValues.push(endpointParts[i]);
//               }
//           }
          
//           // Create a new endpoint with the mapped pattern
//           let mappedEndpoint = newPattern;
//           for (let i = 0; i < paramNames.length; i++) {
//               mappedEndpoint = mappedEndpoint.replace(`:${paramNames[i]}`, paramValues[i]);
//           }
          
//           return mappedEndpoint;
//       }
//   }
  
//   // If no mapping found, return the original endpoint
//   return endpoint;
// }

// /**
// * Enhanced API URL function that handles endpoint mapping
// * @param {string} endpoint - The endpoint to get URL for
// * @returns {string} The complete API URL
// */
// function getApiUrlWithMapping(endpoint) {
//   // Apply mapping if needed
//   const mappedEndpoint = mapApiEndpoint(endpoint);
  
//   // Ensure there's no leading slash
//   const formattedEndpoint = mappedEndpoint.startsWith('/') 
//       ? mappedEndpoint.substring(1) 
//       : mappedEndpoint;
  
//   // Return the complete URL
//   return `/api/${formattedEndpoint}`;
// }

// // Override the original getApiUrl function if it exists
// /**
//  * Enhanced API URL Mapping for PDF Management Dashboard
//  * 
//  * This script fixes compatibility issues between old and new API endpoints
//  * to ensure that the dashboard works correctly with the backend API.
//  */

// // Improved API endpoint mapping function to address the readytoprocess issue
// window.getApiUrl = function(endpoint) {
//   console.log("Original endpoint requested:", endpoint);
  
//   // Handle the specific mappings that were causing issues
//   if (endpoint === 'order-counts/') {
//     return '/api/order-counts/get_counts/';
//   }
  
//   if (endpoint === 'single-orders/') {
//     return '/api/order-counts/get_single_orders/';
//   }
  
//   if (endpoint === 'multi-orders/') {
//     return '/api/order-counts/get_multi_orders/';
//   }
  
//   if (endpoint === 'process-orders/') {
//     return '/api/order-counts/process_orders/';
//   }
  
//   if (endpoint === 'picklists/') {
//     return '/api/picklists/';
//   }
  
//   // Handle parameterized URLs for picklists
//   if (endpoint.startsWith('picklists/') && endpoint.includes('/')) {
//     const parts = endpoint.split('/');
//     const picklistId = parts[1];
//     const action = parts[2] || '';
    
//     // Map different picklist actions
//     if (action === '') {
//       return `/api/picklists/${picklistId}/get_picklist_items/`;
//     } else if (action === 'mark-picked') {
//       return `/api/picklists/${picklistId}/mark_items_picked/`;
//     } else if (action === 'status') {
//       return `/api/picklists/${picklistId}/update_status/`;
//     } else {
//       return `/api/picklists/${picklistId}/${action}/`;
//     }
//   }
  
//   // Handle file processing endpoints
//   if (endpoint === 'pdf-uploads/') {
//     return '/api/pdf-uploads/upload/';
//   }
  
//   if (endpoint === 'process-files/') {
//     return '/api/pdf-uploads/process-files/';
//   }
  
//   // Default case: ensure consistent format with /api/ prefix
//   if (endpoint.startsWith('/')) {
//     endpoint = endpoint.substring(1);
//   }
  
//   // Log the final endpoint for debugging
//   const finalEndpoint = `/api/${endpoint}`;
//   console.log("Mapped to:", finalEndpoint);
//   return finalEndpoint;
// };